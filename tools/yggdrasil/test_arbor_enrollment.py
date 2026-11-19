"""Exercise the portable CLI and the pinned Registry's actual wire format."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import arbor_enrollment as app
from nacl.signing import SigningKey


class EnrollmentTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.authority = SigningKey.generate()
        self.pin = app.encode(self.authority.verify_key)
        self.parser = app.argparse.ArgumentParser()
        app.register(self.parser)

    def invoke(self, *argv):
        args = self.parser.parse_args([argv[0], "--state-dir", str(self.directory), *map(str, argv[1:])])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return args.handler(args)

    def request(self, filename="request.json", node="guest"):
        file = self.directory / filename
        return self.invoke("request", "--out", file, "--node", node, "--authority", "parent",
                           "--authority-key", self.pin)

    def test_request_lifecycle(self):
        self.assertEqual(self.request(), 0)
        self.assertEqual(self.request(), 1)  # output is exclusive
        self.assertEqual(self.request("again"), 0)
        self.assertEqual(self.request("another", "other"), 1)
        read = lambda name: json.loads((self.directory / name).read_bytes())
        first = read("request.json")
        self.assertEqual(first, read("again"))
        with patch.object(app.time, "time", return_value=first["expiresAt"] + 1):
            self.assertEqual(self.request("fresh"), 0)
        self.assertEqual(first["publicKey"], read("fresh")["publicKey"])
        self.assertNotEqual(first["nonce"], read("fresh")["nonce"])

    def test_private_state(self):
        self.assertEqual(self.request(), 0)
        database = self.directory / "enrollment" / "identity.sqlite"
        if os.name == "nt":
            subprocess.run(["icacls.exe", str(database), "/grant", "*S-1-1-0:R"],
                           check=True, capture_output=True)
        else:
            self.assertEqual(database.stat().st_mode & 0o777, 0o600)
            database.chmod(0o644)
        self.assertEqual(self.request("another"), 1)

    def test_actual_registry_approval(self):
        try:
            from arbor_registry_runtime import FileProvider, Runtime, RuntimeKey, approve_enrollment
        except ImportError as error:
            self.skipTest(f"pinned Linux Registry runtime required: {error}")
        self.assertEqual(self.request(), 0)
        request = json.loads((self.directory / "request.json").read_bytes())
        key = RuntimeKey("parent", self.authority)
        record = approve_enrollment(request, key)
        runtime = Runtime(self.directory / "registry", FileProvider(self.directory / "records"),
                          {"parent": key.public_key}, authority_issuers={"parent"})
        self.addCleanup(runtime.db.close)
        self.assertEqual(runtime.ingest([record])[0]["status"], "accepted")
        file = self.directory / "approval"
        forged = approve_enrollment(request, RuntimeKey("parent", SigningKey.generate()))
        for invalid in (forged, {**record, "generation": True}, {**record, "recordId": "other"}):
            file.write_text(json.dumps(invalid))
            self.assertEqual(self.invoke("finish", "--approval", file), 1)
        file.write_text(json.dumps(record))
        self.assertEqual(self.invoke("finish", "--approval", file), 0)
        self.assertEqual(self.invoke("finish", "--approval", file), 0)
        self.assertEqual(self.request("after"), 1)


if __name__ == "__main__":
    unittest.main()
