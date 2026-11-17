from pathlib import Path
import subprocess
import unittest

TOOL = Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/doctor'

class Doctor(unittest.TestCase):
    def test_help_does_not_need_tools(self):
        result = subprocess.run(['/run/current-system/sw/bin/bash', str(TOOL), '--help'], capture_output=True, text=True, env={'PATH': '/nonexistent'})
        self.assertEqual(result.returncode, 0)
        self.assertIn('read-only', result.stdout)

if __name__ == '__main__':
    unittest.main()
