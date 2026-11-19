import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

source = Path(__file__).resolve().parents[2] / "config/machines/raspberry-evolver/firmware-key.py"
spec = importlib.util.spec_from_file_location("firmware_key", source)
keyfile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(keyfile)


class FirmwareKeyTest(unittest.TestCase):
    def test_windows_input_and_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            volume = Path(directory)
            firmware = volume / "tailscale-authkey.txt"
            staged = volume / "private" / "tailscale.authkey"
            with patch.object(keyfile.os.path, "ismount", return_value=True):
                firmware.write_bytes(b"\xef\xbb\xbftskey-auth-FAKE-SENTINEL\r\n")
                self.assertEqual(keyfile.main("stage", volume, staged), 0)
                self.assertEqual(staged.read_bytes(), b"tskey-auth-FAKE-SENTINEL")
                self.assertEqual(staged.stat().st_mode & 0o777, 0o600)
                self.assertEqual(staged.parent.stat().st_mode & 0o777, 0o700)
                for invalid in (b"tskey-auth-FAKE\nsecond", b"$(echo x)", b"\xff", b"x" * 1025):
                    firmware.write_bytes(invalid)
                    self.assertEqual(keyfile.main("stage", volume, staged), 2)
                    self.assertEqual(staged.read_bytes(), b"tskey-auth-FAKE-SENTINEL")
                firmware.write_bytes(b"tskey-auth-OTHER")
                self.assertEqual(keyfile.main("stage", volume, staged), 0)
                self.assertEqual(staged.read_bytes(), b"tskey-auth-OTHER")
                self.assertEqual(keyfile.main("cleanup", volume, staged), 0)
                self.assertFalse(firmware.exists())

    def test_missing_mount_cannot_report_cleanup(self):
        with patch.object(keyfile.os.path, "ismount", return_value=False):
            self.assertEqual(keyfile.main("cleanup", "/unmounted", "/private/auth"), 3)
