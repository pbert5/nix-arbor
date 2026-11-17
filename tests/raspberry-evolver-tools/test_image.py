import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
import hashlib
import json
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/image'
loader = importlib.machinery.SourceFileLoader('image_tool', str(SCRIPT))
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

    def test_help_is_safe_and_personalization_fails_closed(self):
        result = subprocess.run([str(SCRIPT), '--help'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--build-only', result.stdout)
        result = subprocess.run([str(SCRIPT), '--from', '/nonexistent'], text=True, capture_output=True, input='')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('auth key:', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
