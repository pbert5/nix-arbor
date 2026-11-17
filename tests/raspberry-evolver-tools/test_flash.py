import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "tools/raspberry-evolver"))
import contextlib
import copy
import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import stat
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/flash_impl.py'
loader = importlib.machinery.SourceFileLoader('flash', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
flash = importlib.util.module_from_spec(spec)
loader.exec_module(flash)


class FlashTests(unittest.TestCase):
    def test_copy_and_verify_exact_range(self):
        with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as target:
            source.write(b'hello world')
            source.seek(0)
            target.write(b'?' * 100)
            target.seek(0)
            digest = flash.digest(source, 11)
            source.seek(0)
            flash.copy_and_verify(source, target, 11, digest)
            target.seek(11)
            self.assertEqual(target.read(), b'?' * 89)

    def test_short_writes_are_retried(self):
        class ShortWriter:
            def __init__(self, file):
                self.file = file
            def write(self, data):
                return self.file.write(data[:2])
            def __getattr__(self, name):
                return getattr(self.file, name)
        with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as target:
            source.write(b'1234567')
            source.seek(0)
            expected = flash.digest(source, 7)
            source.seek(0)
            flash.copy_and_verify(source, ShortWriter(target), 7, expected)

    def test_copy_detects_short_source_and_bad_readback(self):
        with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as target:
            source.write(b'hello')
            source.seek(0)
            with self.assertRaisesRegex(flash.SafetyError, 'short'):
                flash.copy_and_verify(source, target, 6, '0' * 64)
            source.seek(0)
            target.seek(0)
            with self.assertRaisesRegex(flash.SafetyError, 'verification'):
                flash.copy_and_verify(source, target, 5, '0' * 64)

    def test_graph_rejects_active_or_unresolved_devices(self):
        graph = {'8:0': {'type': 'disk', 'size': 32000000000, 'ro': False,
                          'children': ['8:1'], 'holders': [], 'identity': 'serial'},
                 '8:1': {'type': 'part', 'size': 100, 'ro': False,
                          'children': [], 'holders': [], 'identity': ''},
                 '9:0': {'type': 'disk', 'size': 64000000000, 'ro': False,
                          'children': [], 'holders': [], 'identity': 'source'}}
        flash.validate_graph(graph, '8:0', set(), set(), '9:0', 10)
        graph['8:0']['size'] = 64000000000
        flash.validate_graph(graph, '8:0', set(), set(), '9:0', 10)
        graph['8:0']['size'] = 32000000000
        with self.assertRaises(flash.SafetyError):
            flash.validate_graph(graph, '8:0', set(), set(), '9:0', 33000000000)
        for active, swap, source in [({'8:1'}, set(), '9:0'), (set(), {'8:1'}, '9:0'),
                                     (set(), set(), '8:1')]:
            with self.assertRaises(flash.SafetyError):
                flash.validate_graph(graph, '8:0', active, swap, source, 10)
        for change in ({'holders': ['dm-0']}, {'ro': True}, {'identity': ''},
                       {'size': 100}, {'children': ['missing']}):
            broken = {key: value.copy() for key, value in graph.items()}
            broken['8:0'].update(change)
            with self.assertRaises(flash.SafetyError):
                flash.validate_graph(broken, '8:0', set(), set(), '9:0', 10)
        with self.assertRaises(flash.SafetyError):
            flash.validate_graph(graph, '8:1', set(), set(), '9:0', 10)
        graph['9:0']['type'] = 'virtual'
        with self.assertRaises(flash.SafetyError):
            flash.validate_graph(graph, '8:0', set(), set(), '9:0', 10)

    def test_zpool_requires_resolvable_leaves(self):
        output = """  pool: tank
config:

    NAME              STATE     READ WRITE CKSUM
    tank              ONLINE       0     0     0
      mirror-0        ONLINE       0     0     0
        /dev/a        ONLINE       0     0     0
        /dev/b        ONLINE       0     0     0

errors: No known data errors
"""
        self.assertEqual(flash.zpool_leaves(output), ['/dev/a', '/dev/b'])
        with self.assertRaises(flash.SafetyError):
            flash.zpool_leaves(output.replace('/dev/a', '123456789'))
        with self.assertRaises(flash.SafetyError):
            flash.zpool_leaves('truncated output')

    def test_manifest_must_match_image(self):
        with tempfile.TemporaryDirectory() as directory:
            image = pathlib.Path(directory) / 'image.img'
            image.write_bytes(b'hello')
            manifest = pathlib.Path(str(image) + '.json')
            data = {'schema_version': 1, 'model': 'Raspberry Pi 4', 'hostname': 'raspberry-evolver', 'source_revision': 'a' * 40, 'lock_sha256': 'b' * 64, 'clean_sha256': 'c' * 64, 'personalized': True, 'result_size': 5,
                    'result_sha256': '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'}
            manifest.write_text(json.dumps(data))
            flash.validate_manifest(image, 5, data['result_sha256'])
            incomplete = data.copy()
            del incomplete['model']
            manifest.write_text(json.dumps(incomplete))
            with self.assertRaises(flash.SafetyError):
                flash.validate_manifest(image, 5, data['result_sha256'])
            data['result_size'] = 6
            manifest.write_text(json.dumps(data))
            with self.assertRaises(flash.SafetyError):
                flash.validate_manifest(image, 5, '0' * 64)

    def test_changed_identity_rejected(self):
        with self.assertRaises(flash.SafetyError):
            flash.same_device({'identity': 'a', 'size': 32000000000},
                              {'identity': 'b', 'size': 32000000000})


class FlashConfirmationTests(unittest.TestCase):
    def test_post_confirmation_safety_gates(self):
        # These scenarios execute main's actual ordering; the fake descriptor can
        # never address a real device, even if a guard under test regresses.
        scenarios = ('safe', 'dry_run', 'elevate', 'declined', 'inspection_denied', 'identity', 'mounted', 'swap', 'holder', 'disappeared',
                     'open_disappeared', 'opened_replacement', 'capacity',
                     'final_identity', 'final_mounted', 'final_swap', 'final_holder',
                     'final_disappeared')
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                image = pathlib.Path(directory) / 'image.img'
                image.write_bytes(b'hello')
                pathlib.Path(str(image) + '.json').write_text(json.dumps({
                    'schema_version': 1, 'model': 'Raspberry Pi 4', 'hostname': 'raspberry-evolver',
                    'source_revision': 'a' * 40, 'lock_sha256': 'b' * 64, 'clean_sha256': 'c' * 64,
                    'personalized': True, 'result_size': 5, 'result_sha256': '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'}))
                image_device = image.stat().st_dev
                source_id = f'{os.major(image_device)}:{os.minor(image_device)}'
                target_id = '240:0'
                self.assertNotEqual(source_id, target_id)
                graph = {
                    target_id: {'type': 'disk', 'size': 32000000000, 'ro': False,
                                'children': ['240:1'], 'holders': [], 'identity': 'serial',
                                'model': 'test', 'name': 'fake'},
                    '240:1': {'type': 'part', 'size': 100, 'ro': False, 'children': [],
                              'holders': [], 'identity': '', 'name': 'fake1'},
                    source_id: {'type': 'disk', 'size': 64000000000, 'ro': False,
                                'children': [], 'holders': [], 'identity': 'source'},
                }
                snapshots = [(copy.deepcopy(graph), set(), set()) for _ in range(3)]
                if scenario == 'inspection_denied':
                    snapshots = [PermissionError('unreadable swap')]
                stage = 2 if scenario.startswith('final_') else 1
                reason = scenario.removeprefix('final_')
                if reason == 'identity':
                    snapshots[stage][0][target_id]['identity'] = 'replacement'
                if reason == 'mounted':
                    snapshots[stage][1].add('240:1')
                if reason == 'swap':
                    snapshots[stage][2].add('240:1')
                if reason == 'holder':
                    snapshots[stage][0]['240:1']['holders'].append('dm-0')
                if reason == 'disappeared':
                    del snapshots[stage][0][target_id]

                block = SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=os.makedev(240, 0))
                opened = SimpleNamespace(st_mode=stat.S_IFBLK, st_rdev=os.makedev(
                    240, 2 if scenario == 'opened_replacement' else 0))
                actual_stat, actual_fstat, actual_realpath = os.stat, os.fstat, os.path.realpath
                def fake_stat(path, *args, **kwargs):
                    return block if str(path) == '/dev/fake' else actual_stat(path, *args, **kwargs)
                def fake_realpath(path, *args, **kwargs):
                    return '/dev/fake' if str(path) == '/dev/fake' else actual_realpath(path, *args, **kwargs)
                def fake_fstat(fd):
                    return opened if fd == 123456 else actual_fstat(fd)
                target = MagicMock()
                target.fileno.return_value = 123456
                context = MagicMock()
                context.__enter__.return_value = target
                capacity = 31000000000 if scenario == 'capacity' else 32000000000
                with contextlib.ExitStack() as stack:
                    stack.enter_context(patch.object(sys, 'argv', ['flash', *([] if scenario == 'dry_run' else ['--write']), str(image), '/dev/fake']))
                    stack.enter_context(patch.object(flash.os, 'geteuid', return_value=1000 if scenario in ('dry_run', 'elevate') else 0))
                    elevated = stack.enter_context(patch.object(flash, 'elevate'))
                    stack.enter_context(patch.object(flash, 'instance_lock', return_value=contextlib.nullcontext()))
                    confirm = stack.enter_context(patch('builtins.input', return_value='no' if scenario == 'declined' else '/dev/fake serial 32000000000'))
                    stack.enter_context(patch.object(flash.os.path, 'realpath', side_effect=fake_realpath))
                    stack.enter_context(patch.object(flash.os, 'stat', side_effect=fake_stat))
                    stack.enter_context(patch.object(flash.os, 'fstat', side_effect=fake_fstat))
                    snapshot = stack.enter_context(patch.object(flash, 'snapshot', side_effect=snapshots))
                    open_device = stack.enter_context(patch.object(flash.os, 'open',
                        side_effect=FileNotFoundError('device gone') if scenario == 'open_disappeared' else None,
                        return_value=123456))
                    stack.enter_context(patch.object(flash.os, 'fdopen', return_value=context))
                    stack.enter_context(patch.object(flash.fcntl, 'ioctl', return_value=struct.pack('Q', capacity)))
                    write = stack.enter_context(patch.object(flash, 'copy_and_verify'))
                    output = stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                    if scenario == 'safe':
                        flash.main()
                        write.assert_called_once()
                        self.assertEqual(snapshot.call_count, 3)
                        self.assertEqual(open_device.call_args.args,
                                         ('/dev/fake', os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC))
                    elif scenario in ('dry_run', 'elevate'):
                        flash.main()
                        write.assert_not_called()
                        open_device.assert_not_called()
                        confirm.assert_not_called()
                        self.assertEqual(elevated.call_count, int(scenario == 'elevate'))
                        self.assertEqual(snapshot.call_count, int(scenario == 'dry_run'))
                        if scenario == 'elevate':
                            self.assertIn('Target: /dev/fake (240:0)', output.getvalue())
                            self.assertIn('Privileged read-only inspection', output.getvalue())
                    else:
                        with self.assertRaises((flash.SafetyError, OSError)):
                            flash.main()
                        write.assert_not_called()
                        target.write.assert_not_called()
                        if scenario == 'inspection_denied':
                            confirm.assert_not_called()
                            open_device.assert_not_called()
                        if scenario == 'declined':
                            self.assertEqual(snapshot.call_count, 1)
                            confirm.assert_called_once()
                        if scenario in ('declined', 'identity', 'mounted', 'swap', 'holder', 'disappeared'):
                            open_device.assert_not_called()

class LocalLockTests(unittest.TestCase):
    def test_competing_instances_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'lock')
            real_open = os.open
            real_fstat = os.fstat
            def open_fixture(_path, flags, mode):
                return real_open(path, flags, mode)
            def owner_fixture(fd):
                info = real_fstat(fd)
                return SimpleNamespace(st_mode=info.st_mode, st_uid=0, st_nlink=info.st_nlink)
            with patch.object(flash.os, 'open', side_effect=open_fixture), \
                 patch.object(flash.os, 'fstat', side_effect=owner_fixture):
                with flash.instance_lock('240:0'):
                    with self.assertRaisesRegex(flash.SafetyError, 'another flash'):
                        with flash.instance_lock('240:0'):
                            pass
                with flash.instance_lock('240:0'):
                    pass

class MountNamespaceTests(unittest.TestCase):
    def test_visible_mounts_and_invalid_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'mountinfo'
            path.write_text('1 0 8:1 / / rw - ext4 /dev/test rw\n')
            self.assertEqual(flash.mounted_devices(path), {'8:1'})
            path.write_text('1 0 0:42 / / rw - overlay overlay rw\n')
            with self.assertRaises(flash.SafetyError):
                flash.mounted_devices(path)
            path.write_text('1 0 0:42 / /nix rw - overlay overlay rw\n')
            with self.assertRaises(flash.SafetyError):
                flash.mounted_devices(path)
            path.write_text('invalid\n')
            with self.assertRaises(flash.SafetyError):
                flash.mounted_devices(path)

class EntryPointTests(unittest.TestCase):
    def test_denied_elevation_stops_without_retry(self):
        args = SimpleNamespace(image='image', device='/dev/fake')
        with patch.object(flash.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as sudo:
            with self.assertRaisesRegex(flash.SafetyError, 'no retry'):
                flash.elevate(args)
            sudo.assert_called_once()

    def test_no_args_shows_inventory(self):
        with patch.object(sys, 'argv', ['flash']), patch.object(flash.subprocess, 'run') as run:
            with contextlib.redirect_stdout(io.StringIO()):
                flash.main()
            run.assert_called_once()
            self.assertEqual(run.call_args.args[0][0], 'lsblk')
