import base64
import json
import tempfile
import unittest
from pathlib import Path

from arbor_registry_runtime import FileProvider, Runtime, RuntimeKey, make_identity_generation, make_public_record
from arbor_registry_runtime.registryctl import (
    _private_key,
    _public_generations,
    _record,
    _sync,
    _write_json_atomic,
)
from arbor_registry_runtime.runtime import SigningKey


class CursorProvider(FileProvider):
    def __init__(self, path, pages):
        super().__init__(path)
        self.pages = pages
        self.next_cursor = None

    def fetch(self, cursor=0, limit=100):
        page = self.pages.get(cursor, [])
        self.next_cursor = page[0] if page and isinstance(page[0], str) else cursor
        records = page[1] if page and isinstance(page[0], str) else page
        return list(enumerate(records))


class RegistryCtlTests(unittest.TestCase):
    def test_public_generations_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authorities = root / "authorities.json"
            authorities.write_text(json.dumps({"root": "public-key"}))
            config = {"bootstrapAuthoritiesFile": str(authorities)}
            args = type("Args", (), {
                "issuer": "node", "generation": None, "record_generation": 7,
                "issuer_generation": 3,
            })()
            self.assertEqual(_public_generations(args, config), (7, 3))

            key = RuntimeKey("node", SigningKey.generate())
            record = _record(key, "endpoint", "endpoint-7", {"node": "node"}, 7, 3)
            self.assertEqual(record["generation"], 7)
            self.assertEqual(record["recordVersion"], 7)
            self.assertEqual(record["issuerGeneration"], 3)

    def test_legacy_generation_is_rejected_when_split_flags_are_present(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authorities = root / "authorities.json"
            authorities.write_text(json.dumps({"root": "public-key"}))
            args = type("Args", (), {
                "issuer": "root", "generation": 2, "record_generation": 2,
                "issuer_generation": None,
            })()
            with self.assertRaisesRegex(ValueError, "cannot be combined"):
                _public_generations(args, {"bootstrapAuthoritiesFile": str(authorities)})

    def test_missing_later_issuer_key_does_not_fall_back_to_legacy_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = RuntimeKey("node", SigningKey.generate())
            root.joinpath("node.private").write_text(
                base64.urlsafe_b64encode(bytes(key.signing_key)).decode("ascii").rstrip("=")
            )
            with self.assertRaisesRegex(ValueError, "generation 2 is missing"):
                _private_key(root, "node", 2)

    def test_cursor_is_written_only_after_page_ingest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            key = RuntimeKey("root", SigningKey.generate())
            record = {
                "protocolEpoch": 1, "wireVersion": 1, "schemaVersion": 1,
                "recordVersion": 1, "recordId": "r", "generation": 1,
                "predecessor": None, "issuer": "root", "schema": "endpoint",
                "payload": {"node": "root", "network": "test", "address": "10.0.0.1", "port": 22, "purpose": "ssh"},
            }
            record["signature"] = key.sign({k: v for k, v in record.items()})
            provider = CursorProvider(root / "raw", {"v2:begin": ["v2:next", [record]]})
            runtime = Runtime(root / "state", provider, {"root": key.public_key}, authority_issuers={"root"})
            result = _sync({"stateDir": str(root / "state"), "providerCursorFile": str(root / "cursor.json")}, runtime, provider, 10, 2)
            self.assertEqual(result["accepted"], 1)
            self.assertEqual(json.loads((root / "cursor.json").read_text())["cursor"], "v2:next")
            runtime.close()

    def test_atomic_writer_replaces_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cursor.json"
            _write_json_atomic(path, {"cursor": "v2:one"})
            _write_json_atomic(path, {"cursor": "v2:two"})
            self.assertEqual(json.loads(path.read_text())["cursor"], "v2:two")

    def test_authority_discovered_node_key_requires_current_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            authority = RuntimeKey("root", SigningKey.generate())
            child_one = RuntimeKey("child", SigningKey.generate())
            child_two = RuntimeKey("child", SigningKey.generate())
            provider = FileProvider(root / "raw")
            runtime = Runtime(root / "state", provider, {"root": authority.public_key}, authority_issuers={"root"})
            identity_one = make_identity_generation(authority, "child", 1, child_one.public_key)
            self.assertEqual(runtime.ingest([identity_one])[0]["status"], "accepted")
            endpoint_one = make_public_record(child_one, "endpoint", "child-endpoint", {"node": "child"}, issuer_generation=1)
            self.assertEqual(runtime.ingest([endpoint_one])[0]["status"], "accepted")
            identity_two = make_identity_generation(authority, "child", 2, child_two.public_key, recovery_authorization={"ok": True})
            self.assertEqual(runtime.ingest([identity_two])[0]["status"], "quarantined")
            stale = make_public_record(child_one, "endpoint", "child-stale", {"node": "child"}, issuer_generation=1)
            self.assertEqual(runtime.ingest([stale])[0]["reason"], "stale-issuer-generation")
            runtime.close()


if __name__ == "__main__":
    unittest.main()
