import importlib.machinery
import importlib.util
import io
import json
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/flash'
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
            data = {'schema_version': 1, 'result_size': 5,
                    'result_sha256': '2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824'}
            manifest.write_text(json.dumps(data))
            flash.validate_manifest(image, 5, data['result_sha256'])
            data['result_size'] = 6
            manifest.write_text(json.dumps(data))
            with self.assertRaises(flash.SafetyError):
                flash.validate_manifest(image, 5, '0' * 64)

    def test_changed_identity_rejected(self):
        with self.assertRaises(flash.SafetyError):
            flash.same_device({'identity': 'a', 'size': 32000000000},
                              {'identity': 'b', 'size': 32000000000})
