from pathlib import Path
import os
import subprocess
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/doctor'

class Doctor(unittest.TestCase):
    def test_help_does_not_need_tools(self):
        result = subprocess.run(['/run/current-system/sw/bin/bash', str(TOOL), '--help'], capture_output=True, text=True, env={'PATH': '/nonexistent'})
        self.assertEqual(result.returncode, 0)
        self.assertIn('read-only', result.stdout)

    def test_image_estimate_uses_actual_file_size(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'fixture.img'
            image.write_bytes(b'x' * 1234)
            result = subprocess.run([str(TOOL), '--image', str(image)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('2468 bytes', result.stdout)
            self.assertIn('unverified', result.stdout)
            self.assertIn('e2fsck:', result.stdout)

if __name__ == '__main__':
    unittest.main()
