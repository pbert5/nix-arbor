import importlib.machinery
import importlib.util
from pathlib import Path
import subprocess
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

    def test_help_is_safe_and_personalization_fails_closed(self):
        result = subprocess.run([str(SCRIPT), '--help'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--build-only', result.stdout)
        result = subprocess.run([str(SCRIPT), '--from', '/nonexistent'], text=True, capture_output=True, input='')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('auth key:', result.stderr.lower())


if __name__ == '__main__':
    unittest.main()
