import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/inspect.py'
spec = importlib.util.spec_from_file_location('inspect_evolver', path)
inspect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect)

class Inspection(unittest.TestCase):
    def test_artifact_digest_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'test.img'
            image.write_bytes(b'image fixture')
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            manifest = {'schema_version': 1, 'result_size': image.stat().st_size, 'result_sha256': digest, 'personalized': True}
            self.assertEqual(inspect.verify_artifact(image, manifest), (image.stat().st_size, digest))
            image.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                inspect.verify_artifact(image, manifest)

    def test_remote_name_and_state_are_constrained(self):
        self.assertTrue(inspect.valid_remote('admin@raspberry-evolver.local'))
        for target in ('-oProxyCommand=bad', 'host;bad', 'host name', ''):
            self.assertFalse(inspect.valid_remote(target))
        self.assertEqual(inspect.safe_state('enrolled\n'), 'enrolled')
        self.assertEqual(inspect.safe_state('secret text'), 'indeterminate')

if __name__ == '__main__':
    unittest.main()
