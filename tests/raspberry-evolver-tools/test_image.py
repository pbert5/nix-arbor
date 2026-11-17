import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import hashlib
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/image'
loader = importlib.machinery.SourceFileLoader('image_tool', str(SCRIPT.with_name('image_impl.py')))
spec = importlib.util.spec_from_loader(loader.name, loader)
image = importlib.util.module_from_spec(spec)
loader.exec_module(image)


class ImageTests(unittest.TestCase):
    def test_supported_key_input(self):
        key = 'tskey-auth-FAKE123-example'
        for value in (key, f'curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --auth-key={key}',
                      f'curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up \\\n --auth-key "{key}"'):
            with self.subTest(value=value):
                self.assertEqual(image.parse_key(value), key)

    def test_rejects_ambiguous_or_executable_input(self):
        for value in ('', 'tskey-auth-', 'tskey-auth-FAKE;touch /tmp/unsafe',
                      'curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --auth-key=tskey-auth-A --auth-key=tskey-auth-B',
                      'curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --auth-key=$(touch /tmp/unsafe)',
                      'curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up --auth-key=tskey-auth-A --ssh'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                image.parse_key(value)

    def test_clean_artifact_manifest_and_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.img'
            source.write_bytes(b'clean fixture')
            destination = root / 'output.img'
            manifest = image.write_clean_artifact(source, destination, 'a' * 40, 'b' * 64)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(manifest['result_sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual(manifest['result_size'], len(source.read_bytes()))
            self.assertFalse(manifest['personalized'])
            self.assertEqual(json.loads(Path(str(destination) + '.json').read_text()), manifest)
            self.assertEqual(image.verify_clean_artifact(destination), manifest)
            manifest_file = Path(str(destination) + '.json')
            manifest_file.write_text(json.dumps(dict(manifest, unexpected='fake-sensitive-value')))
            with self.assertRaises(ValueError):
                image.verify_clean_artifact(destination)
            manifest_file.write_text(json.dumps(manifest).replace('{', '{\"schema_version\": 1, ', 1))
            with self.assertRaises(ValueError):
                image.verify_clean_artifact(destination)
            manifest_file.write_text(json.dumps(manifest))
            destination.write_bytes(b'tampered')
            with self.assertRaises(ValueError):
                image.verify_clean_artifact(destination)
            with self.assertRaises(FileExistsError):
                image.write_clean_artifact(source, destination, 'a' * 40, 'b' * 64)

    def test_compressed_clean_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.img'
            source.write_bytes(b'compressed fixture')
            archive = root / 'source.img.zst'
            subprocess.run(['zstd', '-q', str(source), '-o', str(archive)], check=True)
            result = root / 'output.img'
            manifest = image.write_clean_artifact(archive, result, 'a' * 40, 'b' * 64)
            self.assertEqual(result.read_bytes(), source.read_bytes())
            self.assertEqual(manifest['result_size'], source.stat().st_size)

    def test_disposable_partitioned_ext4_personalization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            part = root / 'partition'
            with part.open('wb') as f:
                f.truncate(24 * 1024 * 1024)
            subprocess.run(['mkfs.ext4', '-q', '-F', '-L', 'NIXOS_SD', str(part)], check=True)
            for name in ('/var', '/var/lib', '/etc', '/etc/NetworkManager'):
                subprocess.run(['debugfs', '-w', '-R', 'mkdir ' + name, str(part)], capture_output=True, check=True)
            source = root / 'source.img'
            with source.open('wb') as f:
                f.truncate(32 * 1024 * 1024)
            subprocess.run(['sfdisk', str(source)], input='label: dos\nunit: sectors\n\nstart=2048, size=49152, type=83\n', text=True, capture_output=True, check=True)
            with source.open('r+b') as f, part.open('rb') as src:
                f.seek(2048 * 512)
                f.write(src.read())
            clean = root / 'clean.img'
            image.write_clean_artifact(source, clean, 'a' * 40, 'b' * 64)
            before = image.digest(clean)
            output = root / 'personalized.img'
            wifi = image.portable_wifi('[connection]\ntype=wifi\n[wifi]\nssid=Fixture\n[wifi-security]\nkey-mgmt=wpa-psk\npsk=FAKEsecret123\n')
            image.personalize(clean, output, 'tskey-auth-FAKE123-example', wifi)
            self.assertEqual(image.digest(clean), before)
            failed = root / 'failed.img'
            with mock.patch.object(image, 'debugfs', side_effect=ValueError('fixture failure')):
                with self.assertRaises(ValueError) as error:
                    image.personalize(clean, failed, 'tskey-auth-FAKE123-example')
            self.assertNotIn('tskey-auth-FAKE123-example', str(error.exception))
            self.assertFalse(failed.exists())
            self.assertFalse(Path(str(failed) + '.json').exists())
            self.assertFalse(list(root.glob('staging-*')))
            subprocess.run(['debugfs', '-w', '-R', 'mkdir /var/lib/tailscale', str(part)], capture_output=True, check=True)
            with source.open('r+b') as f, part.open('rb') as src:
                f.seek(2048 * 512)
                f.write(src.read())
            suspect = root / 'suspect.img'
            image.write_clean_artifact(source, suspect, 'a' * 40, 'b' * 64)
            with self.assertRaises(ValueError):
                image.personalize(suspect, root / 'rejected.img', 'tskey-auth-FAKE123-example')
            self.assertFalse((root / 'rejected.img').exists())
            with clean.open('rb') as f, part.open('wb') as dst:
                f.seek(2048 * 512)
                dst.write(f.read(24 * 1024 * 1024))
            (root / 'machine').write_text('fixture-machine-identity')
            subprocess.run(['debugfs', '-w', '-R', 'write machine /etc/machine-id', str(part)], cwd=root, capture_output=True, check=True)
            with source.open('r+b') as f, part.open('rb') as src:
                f.seek(2048 * 512)
                f.write(src.read())
            suspect_machine = root / 'suspect-machine.img'
            image.write_clean_artifact(source, suspect_machine, 'a' * 40, 'b' * 64)
            with self.assertRaises(ValueError):
                image.personalize(suspect_machine, root / 'rejected-machine.img', 'tskey-auth-FAKE123-example')
            cli_directory = root / 'cli'
            cli_directory.mkdir(mode=0o700)
            captured = io.StringIO()
            with mock.patch.object(image, 'private_directory', return_value=cli_directory), \
                 mock.patch.object(image, 'prompt_key', return_value='tskey-auth-FAKE123-example'), \
                 mock.patch.object(image.sys, 'argv', ['image', '--from', str(clean)]), \
                 contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                self.assertEqual(image.main(), 0)
            self.assertNotIn('tskey-auth-FAKE123-example', captured.getvalue())
            self.assertTrue((cli_directory / 'personalized.img.json').exists())
            manifest = json.loads(Path(str(output) + '.json').read_text())
            self.assertTrue(manifest['personalized'])
            with output.open('rb') as f, part.open('wb') as dst:
                f.seek(2048 * 512)
                dst.write(f.read(24 * 1024 * 1024))
            path = '/var/lib/raspberry-evolver/bootstrap/tailscale.authkey'
            stat = subprocess.run(['debugfs', '-R', 'stat ' + path, str(part)], capture_output=True, text=True, check=True).stdout
            self.assertIn('Mode:  0600', stat)
            self.assertIn('User:     0', stat)
            key = subprocess.run(['debugfs', '-R', 'cat ' + path, str(part)], capture_output=True, text=True, check=True).stdout
            self.assertEqual(key, 'tskey-auth-FAKE123-example\n')
            wifi_path = '/etc/NetworkManager/system-connections/raspberry-evolver.nmconnection'
            wifi_stat = subprocess.run(['debugfs', '-R', 'stat ' + wifi_path, str(part)], capture_output=True, text=True, check=True).stdout
            self.assertIn('Mode:  0600', wifi_stat)
            stored = subprocess.run(['debugfs', '-R', 'cat ' + wifi_path, str(part)], capture_output=True, text=True, check=True).stdout
            self.assertIn('ssid=Fixture', stored)
            self.assertIn('psk=FAKEsecret123', stored)

    def test_wifi_psk_transfer_removes_source_identity(self):
        source = """[connection]
id=source
uuid=11111111-1111-1111-1111-111111111111
type=wifi
interface-name=wlan0
[wifi]
ssid=FixtureNetwork
mac-address=00:11:22:33:44:55
[wifi-security]
key-mgmt=wpa-psk
psk=FAKEsecret123
[ipv4]
method=manual
address1=192.0.2.2/24
[ipv6]
method=disabled
"""
        result = image.portable_wifi(source)
        self.assertIn('ssid=FixtureNetwork', result)
        self.assertIn('psk=FAKEsecret123', result)
        self.assertIn('method=auto', result)
        self.assertNotIn('192.0.2', result)
        self.assertNotIn('wlan0', result)
        self.assertNotIn('00:11', result)
        self.assertNotIn('11111111-', result)
        with self.assertRaises(ValueError):
            image.portable_wifi(source.replace('key-mgmt=wpa-psk', 'key-mgmt=wpa-eap'))

    def test_xdg_state_home_and_source_revision_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with mock.patch.dict(os.environ, {'XDG_STATE_HOME': str(root / 'state')}):
                result = image.private_directory()
                self.assertEqual(result.parent, root / 'state' / 'raspberry-evolver')
                self.assertEqual(result.stat().st_mode & 0o777, 0o700)
            with mock.patch.dict(os.environ, {'XDG_STATE_HOME': 'relative'}):
                with self.assertRaises(ValueError):
                    image.private_directory()
            link = root / 'state-link'
            link.symlink_to(root / 'state', target_is_directory=True)
            with mock.patch.dict(os.environ, {'XDG_STATE_HOME': str(link)}):
                with self.assertRaises(OSError):
                    image.private_directory()
            checkout = root / 'checkout'
            checkout.mkdir()
            subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
            with mock.patch.dict(os.environ, {'XDG_STATE_HOME': str(checkout)}):
                with self.assertRaises(OSError):
                    image.private_directory()
            source = root / 'source.img'
            source.write_bytes(b'fixture')
            output = root / 'clean.img'
            image.write_clean_artifact(source, output, 'a' * 41, 'b' * 64)
            with self.assertRaises(ValueError):
                image.verify_clean_artifact(output)

    def test_prompt_accepts_continuations_without_echoing(self):
        with mock.patch.object(image.getpass, 'getpass', side_effect=[
            'curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up \\',
            '--auth-key=tskey-auth-FAKE123-example']):
            self.assertEqual(image.prompt_key(), 'tskey-auth-FAKE123-example')

    def test_help_is_safe_and_personalization_fails_closed(self):
        environment = dict(os.environ, PATH='/run/current-system/sw/bin:/etc/profiles/per-user/ash/bin')
        result = subprocess.run([str(SCRIPT), '--help'], text=True, capture_output=True, env=environment)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--build-only', result.stdout)
        result = subprocess.run([str(SCRIPT), '--from', '/nonexistent'], text=True, capture_output=True, input='')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('auth key:', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
