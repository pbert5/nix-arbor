import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / "tools/raspberry-evolver"))
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[2] / 'tools/raspberry-evolver/status_impl.py'
spec = importlib.util.spec_from_file_location('inspect_evolver', path)
inspect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspect)

class Inspection(unittest.TestCase):
    def test_artifact_digest_and_size(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'test.img'
            image.write_bytes(b'image fixture')
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            manifest = {'schema_version': 1, 'model': 'Raspberry Pi 4', 'hostname': 'raspberry-evolver', 'source_revision': 'a' * 40, 'lock_sha256': 'b' * 64, 'clean_sha256': 'c' * 64, 'result_size': image.stat().st_size, 'result_sha256': digest, 'personalized': True}
            self.assertEqual(inspect.verify_artifact(image, manifest), (image.stat().st_size, digest))
            for invalid in (None, [], {}, {**manifest, 'model': 'wrong'}):
                with self.assertRaises(ValueError):
                    inspect.verify_artifact(image, invalid)
            manifest['personalized'] = 'unknown'
            with self.assertRaises(ValueError):
                inspect.verify_artifact(image, manifest)
            manifest['personalized'] = True
            image.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                inspect.verify_artifact(image, manifest)

    def test_remote_name_and_state_are_constrained(self):
        self.assertTrue(inspect.valid_remote('admin@raspberry-evolver.local'))
        for target in ('-oProxyCommand=bad', 'host;bad', 'host name', ''):
            self.assertFalse(inspect.valid_remote(target))
        self.assertEqual(inspect.safe_state('enrolled\n'), 'enrolled')
        self.assertEqual(inspect.safe_state('needs-new-key\n'), 'needs-new-key')
        self.assertEqual(inspect.safe_state('secret text'), 'indeterminate')

if __name__ == '__main__':
    unittest.main()
