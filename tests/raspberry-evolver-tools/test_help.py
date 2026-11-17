from pathlib import Path
import subprocess
import unittest

class Help(unittest.TestCase):
    def test_flash_help_needs_no_python_or_nix(self):
        script = Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/flash'
        result = subprocess.run(['/run/current-system/sw/bin/bash', str(script), '--help'], env={'PATH': '/nonexistent'}, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn('--write', result.stdout)
