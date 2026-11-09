#!/usr/bin/env python3
import json
import pathlib
import subprocess
import tempfile
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / 'tools/ssh/add-key'

class AddKeyTest(unittest.TestCase):
    def test_scoped_key_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            (root / 'config/access').mkdir(parents=True)
            for host in ('r640-0', 'eVolver'):
                (root / 'config/machines' / host).mkdir(parents=True)
                (root / 'config/machines' / host / 'default.nix').touch()
            keyfile = root / 'key'
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(keyfile)], check=True)
            key = keyfile.with_suffix('.pub').read_text().strip()
            def run(answer):
                return subprocess.run([sys.executable, str(TOOL), '--root', str(root)], input=answer, text=True, capture_output=True)
            self.assertEqual(run(f'{key}\n0\n1\ny\n').returncode, 0)
            data = json.loads((root / 'config/access/extra-keys.json').read_text())
            self.assertEqual(data, {'r640-0': {'madeline': [key]}})
            self.assertNotEqual(run('not a public key\n').returncode, 0)
            self.assertEqual(json.loads((root / 'config/access/extra-keys.json').read_text()), data)
            self.assertEqual(run(f'{key}\n\n\ny\n').returncode, 0)
            data = json.loads((root / 'config/access/extra-keys.json').read_text())
            self.assertEqual(data['r640-0']['madeline'], [key])
            self.assertEqual(data['eVolver']['ash'], [key])
            self.assertEqual(data['eVolver']['madeline'], [key])

if __name__ == '__main__':
    unittest.main()
