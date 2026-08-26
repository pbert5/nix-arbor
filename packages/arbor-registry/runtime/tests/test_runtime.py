import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from nacl.signing import SigningKey

from arbor_registry_runtime import FileProvider, OrbitDBProvider, Provider, Runtime, RuntimeKey, canonical_json, generate_keypair, make_public_record
from arbor_registry_runtime.runtime import (
    approve_enrollment,
    make_identity_generation,
    make_lifecycle_record,
    make_recovery_approval,
    make_recovery_authorization,
    make_revocation,
    make_receipt,
    make_enrollment_request,
)
from arbor_registry_runtime.runtime import _key
from arbor_registry_runtime.openbao_provider import _json_value


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        key = RuntimeKey("root", SigningKey.generate())
        self.runtime = Runtime(root / "state", FileProvider(root / "raw" / "history.jsonl"), {"root": key.public_key})
        self.key = key

    def tearDown(self):
        self.runtime.close()
        self.temp.cleanup()

    def envelope(self, record_id, generation=1, predecessor=None, schema="node-identity", payload=None, record_version=1):
        record = {"protocolEpoch": 1, "wireVersion": 1, "schemaVersion": 1, "recordVersion": record_version,
                  "recordId": record_id, "generation": generation, "predecessor": predecessor,
                  "issuer": "root", "schema": schema, "payload": payload or {"id": record_id}}
        record["signature"] = self.key.sign({k: v for k, v in record.items() if k != "signature"})
        return record

    def test_partition_reorder_and_materialization(self):
        parent = self.envelope("node", payload={"id": "node", "aliases": ["old"]})
        child = self.envelope("node", 2, "node", payload={"id": "node", "aliases": ["new"]}, record_version=2)
        self.assertEqual(self.runtime.ingest([child])[0]["status"], "quarantined")
        self.assertEqual(self.runtime.projection(), {})
        self.runtime.ingest([parent])
        self.assertEqual(self.runtime.projection()["node"]["payload"]["aliases"], ["new"])

    def test_replay_is_idempotent_and_raw_history_is_append_only(self):
        record = self.envelope("one")
        self.runtime.ingest([record, record])
        self.assertEqual(len(self.runtime.accepted()), 1)
        raw = Path(self.temp.name) / "raw" / "history.jsonl"
        self.assertEqual(len(raw.read_text().splitlines()), 1)

    def test_invalid_signature_and_unknown_record_are_quarantined(self):
        invalid = self.envelope("bad")
        invalid["payload"]["id"] = "tampered"
        unknown = self.envelope("future", schema="future-record")
        self.runtime.ingest([invalid, unknown])
        reasons = {item["reason"] for item in self.runtime.quarantine()}
        self.assertEqual(reasons, {"invalid-signature", "unknown-schema"})

    def test_bounded_cursors(self):
        self.runtime.ingest([self.envelope("one"), self.envelope("two")])
        self.assertEqual([r["recordId"] for r in self.runtime.accepted(1, 1)], ["two"])
        with self.assertRaises(ValueError):
            self.runtime.accepted(0, 1001)

    def test_provider_contract_is_durable_idempotent_and_cursor_bounded(self):
        provider = self.runtime.provider
        self.assertIsInstance(provider, Provider)
        first = self.envelope("one")
        second = self.envelope("two")
        self.assertEqual(provider.append(first), 0)
        self.assertEqual(provider.append(first), 0)
        self.assertEqual(provider.append(second), 1)
        self.assertEqual(provider.fetch(0, 1), [(0, first)])
        self.assertEqual(provider.fetch(1, 1000), [(1, second)])
        with self.assertRaises(ValueError):
            provider.fetch(0, 1001)

    def test_public_state_has_no_private_key_material(self):
        self.runtime.ingest([self.envelope("one")])
        files = list(Path(self.temp.name, "state").rglob("*"))
        self.assertFalse(any(path.name.endswith(".private") for path in files))
        self.assertNotIn(bytes(self.key.signing_key).hex(), json.dumps(self.runtime.projection()))
        self.assertTrue(canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}')

    def test_relationship_authority_matches_delegated_pure_model(self):
        root_a = self.key
        root_b = RuntimeKey("root-b", SigningKey.generate())
        child = RuntimeKey("child", SigningKey.generate())
        grandchild = RuntimeKey("grandchild", SigningKey.generate())
        stranger = RuntimeKey("stranger", SigningKey.generate())
        runtime = Runtime(
            Path(self.temp.name) / "authority-state",
            FileProvider(Path(self.temp.name) / "authority-raw" / "history.jsonl"),
            {"root": root_a.public_key, "root-b": root_b.public_key},
            authority_issuers={"root", "root-b"},
        )

        def edge(key, record_id, source, target, kind="parent", status="active", root="root", scope=("observe",)):
            return make_public_record(
                key,
                "relationship" if kind != "peer" else "peer-relationship",
                record_id,
                {"from": source, "to": target, "kind": kind, "status": status,
                 "authorityRoot": root, "scope": list(scope)},
                issuer_generation=None if key.issuer in {"root", "root-b"} else 1,
            )

        base = [
            make_identity_generation(root_a, "child", 1, child.public_key),
            make_identity_generation(root_a, "grandchild", 1, grandchild.public_key),
            make_identity_generation(root_a, "stranger", 1, stranger.public_key),
            edge(root_a, "peer-root-root-b", "root", "root-b", "peer", root="root"),
            edge(root_a, "root-child", "root", "child", scope=("observe",)),
            edge(root_b, "root-b-child-standby", "root-b", "child", status="standby", root="root-b"),
            edge(child, "child-grandchild", "child", "grandchild", root="root", scope=("observe",)),
        ]
        outcomes = runtime.ingest(base)
        by_id = {item["recordKey"].split(":")[0]: item for item in outcomes}
        self.assertEqual(by_id["peer-root-root-b"]["status"], "accepted")
        self.assertEqual(by_id["root-child"]["status"], "accepted")
        self.assertEqual(by_id["root-b-child-standby"]["status"], "accepted")
        self.assertEqual(by_id["child-grandchild"]["status"], "accepted")

        outcomes = runtime.ingest([
            edge(stranger, "stranger-child", "stranger", "child", root="root"),
            edge(child, "child-forged-root-b", "child", "grandchild", root="root-b"),
            edge(child, "child-amplifies", "child", "grandchild", root="root", scope=("admin",)),
        ])
        by_id = {item["recordKey"].split(":")[0]: item for item in outcomes}
        self.assertEqual(by_id["stranger-child"]["reason"], "unauthorized-relationship")
        self.assertEqual(by_id["child-forged-root-b"]["reason"], "unauthorized-relationship")
        self.assertEqual(by_id["child-amplifies"]["reason"], "unauthorized-capability")

        outcomes = runtime.ingest([edge(grandchild, "grandchild-cycle", "grandchild", "root", root="root")])
        by_id = {item["recordKey"].split(":")[0]: item for item in outcomes}
        self.assertEqual(by_id["grandchild-cycle"]["reason"], "parent-cycle")
        self.assertEqual(runtime.projection()["root-b-child-standby"]["payload"]["status"], "standby")
        self.assertNotIn("stranger-child", runtime.projection())
        runtime.close()

    def test_delegated_lifecycle_authority_requires_an_explicit_schema_grant(self):
        child = RuntimeKey("child", SigningKey.generate())
        runtime = Runtime(
            Path(self.temp.name) / "delegated-lifecycle-state",
            FileProvider(Path(self.temp.name) / "delegated-lifecycle-raw" / "history.jsonl"),
            {"root": self.key.public_key},
        )
        try:
            identity = make_identity_generation(self.key, "child", 1, child.public_key)
            relationship = make_public_record(
                self.key, "relationship", "root-child",
                {"from": "root", "to": "child", "kind": "parent", "scope": ["observe"],
                 "authorityRoot": "root"},
            )
            revocation = make_lifecycle_record(
                child, "revocation", "child:revocation:1",
                {"identity": "other", "generation": 1, "reason": "retired"},
            )
            revocation["issuerGeneration"] = 1
            revocation["signature"] = child.sign({key: value for key, value in revocation.items() if key != "signature"})
            self.assertEqual(runtime.ingest([identity, relationship, revocation])[-1]["reason"], "unauthorized-authority")

            grant = make_public_record(
                self.key, "relationship", "root-child-revocation",
                {"from": "root", "to": "child", "kind": "parent", "scope": ["revocation"],
                 "authorityRoot": "root"},
            )
            authorized = dict(revocation, recordId="child:revocation:2")
            authorized["signature"] = child.sign({key: value for key, value in authorized.items() if key != "signature"})
            self.assertEqual(runtime.ingest([grant, authorized])[-1]["status"], "accepted")
        finally:
            runtime.close()

    def test_revoked_or_retired_dynamic_generation_cannot_publish(self):
        child = RuntimeKey("child", SigningKey.generate())
        runtime = Runtime(
            Path(self.temp.name) / "dynamic-state",
            FileProvider(Path(self.temp.name) / "dynamic-raw" / "history.jsonl"),
            {"root": self.key.public_key},
        )
        try:
            identity = make_identity_generation(self.key, "child", 1, child.public_key)
            relationship = make_public_record(
                self.key, "relationship", "root-child",
                {"from": "root", "to": "child", "kind": "parent", "scope": ["observe"],
                 "authorityRoot": "root"},
            )
            endpoint = make_public_record(
                child, "endpoint", "child-endpoint", {"node": "child", "address": "https://example.invalid"},
                issuer_generation=1,
            )
            self.assertEqual({item["status"] for item in runtime.ingest([identity, relationship, endpoint])}, {"accepted"})
            revoked = make_revocation(self.key, "child", 1, "compromised")
            self.assertEqual(runtime.ingest([revoked])[-1]["status"], "accepted")
            retired = make_public_record(
                child, "service", "child-service", {"node": "child", "name": "demo"}, issuer_generation=1,
            )
            self.assertEqual(runtime.ingest([retired])[0]["reason"], "revoked-generation")
            self.assertNotIn("child-endpoint", runtime.projection())

            retired_key = RuntimeKey("retired", SigningKey.generate())
            retired_generation = make_lifecycle_record(
                self.key, "identity-generation", "retired", {
                    "identity": "retired", "publicKey": retired_key.public_key,
                    "generation": 1, "status": "deprecated",
                },
            )
            retired_public = make_public_record(
                retired_key, "machine-facts", "retired-facts", {"node": "retired"}, issuer_generation=1,
            )
            self.assertEqual(runtime.ingest([retired_generation, retired_public])[-1]["reason"], "inactive-generation")
        finally:
            runtime.close()

    def test_invalid_recovery_generation_cannot_seed_same_batch_dependent(self):
        child = RuntimeKey("child", SigningKey.generate())
        identity_one = make_identity_generation(self.key, "child", 1, child.public_key)
        invalid_identity_two = make_identity_generation(
            self.key, "child", 2, child.public_key, predecessor="child:1",
            recovery_authorization={"authorization": "not-a-record"},
        )
        dependent = make_public_record(
            child, "endpoint", "child-endpoint-generation-two",
            {"node": "child", "address": "https://example.invalid"}, issuer_generation=2,
        )

        outcomes = self.runtime.ingest([identity_one, invalid_identity_two, dependent])

        self.assertEqual([item["status"] for item in outcomes], ["accepted", "quarantined", "quarantined"])
        self.assertEqual(outcomes[1]["reason"], "missing-recovery-authorization")
        self.assertEqual(outcomes[2]["reason"], "stale-issuer-generation")
        self.assertNotIn("child-endpoint-generation-two", self.runtime.projection())
        self.assertNotIn(("child", 2), self.runtime.dynamic_generations)

    def test_node_bound_public_records_require_matching_node(self):
        for schema in ("endpoint", "service", "machine-facts"):
            missing = self.envelope(f"{schema}-missing", schema=schema, payload={})
            conflicting = self.envelope(f"{schema}-conflicting", schema=schema, payload={"node": "other"})
            outcomes = self.runtime.ingest([missing, conflicting])
            self.assertEqual([item["reason"] for item in outcomes], ["missing-node-binding", "issuer-node-mismatch"])

    def test_generate_keypair_refuses_implicit_overwrite_and_supports_explicit_rotation(self):
        key_dir = Path(self.temp.name) / "identity"
        first = generate_keypair(key_dir, "operator")
        with self.assertRaises(FileExistsError):
            generate_keypair(key_dir, "operator")
        rotated = generate_keypair(key_dir, "operator", rotation=True)
        self.assertNotEqual(first.public_key, rotated.public_key)

    def test_generate_keypair_preserves_prior_generations(self):
        key_dir = Path(self.temp.name) / "identity"
        first = generate_keypair(key_dir, "operator", generation=1)
        second = generate_keypair(key_dir, "operator", generation=2)
        self.assertNotEqual(first.public_key, second.public_key)
        self.assertTrue((key_dir / "operator.g1.private").exists())
        self.assertTrue((key_dir / "operator.g2.private").exists())

    def test_generate_keypair_rejects_path_traversal_and_absolute_issuers(self):
        key_dir = Path(self.temp.name) / "identity"
        for issuer in ("../escape", "nested/operator", "\\absolute", "/absolute", ".", ".."):
            with self.assertRaises(ValueError):
                generate_keypair(key_dir, issuer)

    def test_orbitdb_provider_maps_bounded_socket_contract(self):
        import socketserver
        import threading

        seen = {}

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                seen.update(json.loads(self.rfile.readline()))
                self.wfile.write(json.dumps({"ok": True, "records": [{"hash": "h1", "sequence": 7, "event": {"id": 1}}], "nextCursor": "v1:8"}).encode() + b"\n")

        path = Path(self.temp.name) / "registry.sock"
        server = socketserver.UnixStreamServer(str(path), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = OrbitDBProvider(path, "membership", token="secret")
            self.assertEqual(provider.fetch(0, 1), [(7, {"id": 1})])
            self.assertEqual(seen["cursor"], "v1:0")
            self.assertEqual(seen["token"], "secret")
            self.assertEqual(provider.next_cursor, "v1:8")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_orbitdb_provider_requires_append_cursor(self):
        import socketserver
        import threading

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(json.dumps({"ok": True, "hash": "h1"}).encode() + b"\n")

        path = Path(self.temp.name) / "append.sock"
        server = socketserver.UnixStreamServer(str(path), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with self.assertRaises(ValueError):
                OrbitDBProvider(path, "membership").append({"id": 1})
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_orbitdb_provider_rejects_reordered_sequences(self):
        import socketserver
        import threading

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(json.dumps({
                    "ok": True,
                    "records": [
                        {"hash": "h1", "sequence": 2, "event": {"id": 1}},
                        {"hash": "h2", "sequence": 2, "event": {"id": 2}},
                    ],
                    "nextCursor": "v1:3",
                }).encode() + b"\n")

        path = Path(self.temp.name) / "ordered.sock"
        server = socketserver.UnixStreamServer(str(path), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with self.assertRaises(ValueError):
                OrbitDBProvider(path, "membership").fetch(0, 2)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_envelope_compatibility_and_unsafe_values_are_quarantined(self):
        cases = {
            "unknown-epoch": {"protocolEpoch": 2},
            "unsupported-wire-version": {"wireVersion": 2},
            "unsupported-schema-version": {"schemaVersion": 2},
            "unsupported-required-feature": {"requiredFeatures": ["future"]},
            "unsafe-value": {"payload": {"path": "/run/secrets/token"}},
        }
        records = []
        for changes in cases.values():
            record = self.envelope(changes.get("recordId", "compat" + str(len(records))), payload={"id": "x"})
            record.update(changes)
            record["signature"] = self.key.sign({k: v for k, v in record.items() if k != "signature"})
            records.append(record)
        outcomes = self.runtime.ingest(records)
        self.assertEqual([outcome["reason"] for outcome in outcomes], list(cases))
        self.assertEqual(self.runtime.accepted(), [])

    def test_endpoint_credentials_embedded_in_urls_are_quarantined(self):
        record = self.envelope(
            "endpoint-url",
            schema="endpoint",
            payload={"address": "https://user:password@example.invalid/api"},
        )
        outcome = self.runtime.ingest([record])[0]
        self.assertEqual(outcome["status"], "quarantined")
        self.assertEqual(outcome["reason"], "unsafe-value")

    def test_endpoint_secret_query_credentials_are_redacted_before_persistence(self):
        secret = "do-not-store-this-query-secret"
        records = [
            self.envelope(
                f"endpoint-query-{name}",
                schema="endpoint",
                payload={"node": "root", "address": f"https://example.invalid/api?{name}={secret}"},
            )
            for name in ("token", "access_token", "api-key", "password", "private_key")
        ]

        outcomes = self.runtime.ingest(records)

        self.assertEqual([item["reason"] for item in outcomes], ["unsafe-value"] * len(records))
        self.assertEqual(self.runtime.accepted(), [])
        self.assertEqual(self.runtime.projection(), {})
        self.assertNotIn(secret, json.dumps(self.runtime.quarantine()))
        raw = Path(self.temp.name) / "raw" / "history.jsonl"
        self.assertFalse(raw.exists())
        self.assertNotIn(secret.encode(), (Path(self.temp.name) / "state" / "registry.sqlite3").read_bytes())

    def test_endpoint_urls_with_non_secret_queries_remain_usable(self):
        record = self.envelope(
            "endpoint-benign-query",
            schema="endpoint",
            payload={"node": "root", "address": "https://example.invalid/api?region=eu-west-1"},
        )

        outcome = self.runtime.ingest([record])[0]

        self.assertEqual(outcome["status"], "accepted")
        self.assertEqual(
            self.runtime.projection()["endpoint-benign-query"]["payload"]["address"],
            "https://example.invalid/api?region=eu-west-1",
        )

    def test_bearer_values_are_quarantined_even_without_secret_field_names(self):
        record = self.envelope(
            "endpoint-bearer",
            schema="endpoint",
            payload={"authorization": "Bearer runtime-secret"},
        )
        outcome = self.runtime.ingest([record])[0]
        self.assertEqual(outcome["status"], "quarantined")
        self.assertEqual(outcome["reason"], "unsafe-value")

    def test_conflicting_record_key_quarantines_both_variants(self):
        first = self.envelope("same")
        second = self.envelope("same", payload={"id": "different"})
        outcomes = self.runtime.ingest([first, second])
        self.assertEqual([outcome["reason"] for outcome in outcomes], ["conflicting-record-key", "conflicting-record-key"])
        self.assertEqual(self.runtime.accepted(), [])
        self.assertEqual({item["reason"] for item in self.runtime.quarantine()}, {"conflicting-record-key"})

    def test_forks_and_rollbacks_never_enter_accepted_state(self):
        parent = self.envelope("parent")
        fork_a = self.envelope("a", 2, "parent")
        fork_b = self.envelope("b", 2, "parent")
        self.runtime.ingest([parent, fork_a, fork_b])
        self.assertEqual(self.runtime.accepted(), [parent])
        self.assertEqual({item["reason"] for item in self.runtime.quarantine()}, {"forked-lineage"})
        newer = self.envelope("rollback", 2, "rollback", record_version=2)
        old = self.envelope("rollback", 1)
        # The generation-two record is invalid until its predecessor exists;
        # once both arrive, the stale generation-one record is not accepted.
        self.runtime.ingest([newer, old])
        accepted_keys = {_key(record) for record in self.runtime.accepted()}
        self.assertIn("rollback:2", accepted_keys)
        self.assertNotIn("rollback:1", accepted_keys)
        self.assertIn("anti-rollback", {item["reason"] for item in self.runtime.quarantine()})

    def test_enrollment_is_authority_approved_and_lifecycle_families_are_accepted(self):
        node_key = RuntimeKey("node", SigningKey.generate())
        request = make_enrollment_request(node_key, "node", platform="linux", nonce="abcdefghijklmnop")
        identity = approve_enrollment(request, self.key)
        self.assertEqual(self.runtime.ingest([identity])[0]["status"], "accepted")
        records = [
            make_lifecycle_record(self.key, "enrollment", "enrollment:node", {
                "identity": "node", "publicKey": node_key.public_key,
                "requestDigest": "request", "approvedBy": "root",
            }),
            make_revocation(self.key, "other", 1, "retired"),
            make_receipt(self.key, "node", "digest"),
        ]
        self.assertEqual([item["status"] for item in self.runtime.ingest(records)], ["accepted"] * 3)

    def test_active_generation_and_revocation_gate_validation_and_projection(self):
        generation_one = make_identity_generation(self.key, "node", 1, "old-key")
        generation_two = make_identity_generation(
            self.key, "other", 2, "new-key", predecessor="other:1",
            recovery_authorization={"authorization": "approved"},
        )
        generation_two["payload"]["recoveryAuthorizationDigest"] = "not-the-digest"
        generation_two["signature"] = self.key.sign({key: value for key, value in generation_two.items() if key != "signature"})
        self.assertEqual(self.runtime.ingest([generation_one])[0]["status"], "accepted")
        self.assertEqual(self.runtime.ingest([generation_two])[0]["reason"], "missing-recovery-authorization")

        authorization = make_recovery_authorization(
            self.key, "node", 1, "new-key",
            [make_recovery_approval(self.key, "node", 1, role="operator", approver_generation=1)],
        )
        generation_two = make_identity_generation(
            self.key, "node", 2, "new-key", predecessor="node:1", recovery_authorization=authorization,
        )
        self.assertEqual(self.runtime.ingest([authorization, generation_two])[1]["status"], "accepted")
        event = self.envelope("event", payload={"identity": "node", "identityGeneration": 1})
        self.assertEqual(self.runtime.ingest([event])[0]["reason"], "stale-generation")
        revoked = make_revocation(self.key, "node", 2, "compromised")
        self.runtime.ingest([revoked])
        self.assertNotIn("node:2", {record["recordId"] for record in self.runtime.accepted()})

    def test_recovery_generation_replays_out_of_order_and_rejects_stale_approver(self):
        operator = RuntimeKey("operator", SigningKey.generate())
        replacement = RuntimeKey("node-replacement", SigningKey.generate())
        runtime = Runtime(
            Path(self.temp.name) / "recovery-state",
            FileProvider(Path(self.temp.name) / "recovery-raw" / "history.jsonl"),
            {"root": self.key.public_key, "operator": operator.public_key},
            approver_roles={"operator": {"operator"}, "parent": set(), "peer": set()},
        )
        try:
            operator_generation = make_identity_generation(self.key, "operator", 1, operator.public_key)
            lost = make_identity_generation(self.key, "node", 1, "old-key")
            revoked = make_revocation(self.key, "node", 1, "lost-key")
            approval = make_recovery_approval(operator, "node", 1, role="operator", approver_generation=1)
            authorization = make_recovery_authorization(self.key, "node", 1, replacement.public_key, [approval])
            recovered = make_identity_generation(
                self.key, "node", 2, replacement.public_key,
                predecessor="node:1", recovery_authorization=authorization,
            )

            outcomes = runtime.ingest([recovered, authorization, lost, operator_generation, revoked])
            self.assertEqual({item["status"] for item in outcomes}, {"accepted", "quarantined"})
            self.assertEqual(runtime.projection()["node"]["generation"], 2)
            self.assertEqual(
                {(record["recordId"], record["generation"]) for record in runtime.accepted()},
                {
                    ("node", 2), ("operator", 1),
                    ("node:recovery:1", 1), ("node:revocation:1", 1),
                },
            )

            current_operator = make_identity_generation(self.key, "operator", 2, "new-operator-key")
            runtime.ingest([current_operator])
            self.assertIn(
                "stale-approver-generation",
                {item["reason"] for item in runtime.quarantine()},
            )
            self.assertEqual(runtime.projection()["node"]["generation"], 2)
        finally:
            runtime.close()

    def test_recovery_approvals_are_signed_and_bound_to_lost_generation(self):
        approval = make_recovery_approval(self.key, "node", 1, role="operator", approver_generation=1)
        authorization = make_recovery_authorization(self.key, "node", 1, "new-key", [approval])
        self.assertEqual(self.runtime.ingest([authorization])[0]["status"], "accepted")
        tampered = dict(approval, subject="other")
        bad = make_recovery_authorization(self.key, "other", 1, "new-key", [tampered])
        self.assertEqual(self.runtime.ingest([bad])[0]["reason"], "invalid-recovery-approval-signature")

    def test_dynamic_recovery_approval_requires_current_accepted_generation(self):
        approver = RuntimeKey("approver", SigningKey.generate())
        runtime = Runtime(
            Path(self.temp.name) / "dynamic-approver-state",
            FileProvider(Path(self.temp.name) / "dynamic-approver-raw" / "history.jsonl"),
            {"root": self.key.public_key},
            approver_roles={"operator": {"approver", "root"}, "parent": set(), "peer": set()},
        )
        try:
            approver_identity = make_identity_generation(self.key, "approver", 1, approver.public_key)
            self.assertEqual(runtime.ingest([approver_identity])[0]["status"], "accepted")

            approval = make_recovery_approval(approver, "node", 1, role="operator", approver_generation=1)
            authorization = make_recovery_authorization(self.key, "node", 1, "replacement", [approval])
            self.assertEqual(runtime.ingest([authorization])[0]["status"], "accepted")
        finally:
            runtime.close()

    def test_dynamic_recovery_approval_rejects_stale_generation_after_rotation(self):
        approver_one = RuntimeKey("approver", SigningKey.generate())
        approver_two = RuntimeKey("approver", SigningKey.generate())
        runtime = Runtime(
            Path(self.temp.name) / "rotated-approver-state",
            FileProvider(Path(self.temp.name) / "rotated-approver-raw" / "history.jsonl"),
            {"root": self.key.public_key},
            approver_roles={"operator": {"approver", "root"}, "parent": set(), "peer": set()},
        )
        try:
            first = make_identity_generation(self.key, "approver", 1, approver_one.public_key)
            self.assertEqual(runtime.ingest([first])[0]["status"], "accepted")
            rotation_approval = make_recovery_approval(
                self.key, "approver", 1, role="operator", approver_generation=1,
            )
            rotation = make_recovery_authorization(
                self.key, "approver", 1, approver_two.public_key, [rotation_approval],
            )
            second = make_identity_generation(
                self.key, "approver", 2, approver_two.public_key,
                predecessor="approver:1", recovery_authorization=rotation,
            )
            self.assertEqual({item["status"] for item in runtime.ingest([rotation, second])}, {"accepted"})

            stale = make_recovery_authorization(
                self.key, "node", 1, "replacement",
                [make_recovery_approval(approver_one, "node", 1, role="operator", approver_generation=1)],
            )
            self.assertEqual(runtime.ingest([stale])[0]["reason"], "stale-approver-generation")
        finally:
            runtime.close()

    def test_unaccepted_dynamic_recovery_approver_is_not_authoritative(self):
        approver = RuntimeKey("approver", SigningKey.generate())
        runtime = Runtime(
            Path(self.temp.name) / "unaccepted-approver-state",
            FileProvider(Path(self.temp.name) / "unaccepted-approver-raw" / "history.jsonl"),
            {"root": self.key.public_key},
            approver_roles={"operator": {"approver"}, "parent": set(), "peer": set()},
        )
        try:
            unaccepted = make_identity_generation(self.key, "approver", 1, approver.public_key)
            unaccepted["payload"]["status"] = "deprecated"
            unaccepted["signature"] = self.key.sign(
                {key: value for key, value in unaccepted.items() if key != "signature"}
            )
            approval = make_recovery_approval(approver, "node", 1, role="operator", approver_generation=1)
            authorization = make_recovery_authorization(self.key, "node", 1, "replacement", [approval])
            self.assertEqual(runtime.ingest([unaccepted, authorization])[1]["status"], "quarantined")
            self.assertEqual(runtime.quarantine()[-1]["reason"], "stale-approver-generation")
        finally:
            runtime.close()

    def test_observe_only_child_cannot_seed_same_batch_recovery_approver(self):
        child = RuntimeKey("child", SigningKey.generate())
        approver = RuntimeKey("approver", SigningKey.generate())
        runtime = Runtime(
            Path(self.temp.name) / "same-batch-delegated-approver-state",
            FileProvider(Path(self.temp.name) / "same-batch-delegated-approver-raw" / "history.jsonl"),
            {"root": self.key.public_key},
            approver_roles={"operator": {"approver"}, "parent": set(), "peer": set()},
        )
        try:
            established = [
                make_identity_generation(self.key, "child", 1, child.public_key),
            ]
            self.assertEqual({item["status"] for item in runtime.ingest(established)}, {"accepted"})

            relationship = make_public_record(
                self.key, "relationship", "root-child-observe",
                {"from": "root", "to": "child", "kind": "parent", "scope": ["observe"],
                 "authorityRoot": "root"},
            )
            forged_identity = make_lifecycle_record(
                child, "identity-generation", "approver-from-child", {
                    "identity": "approver", "generation": 1, "publicKey": approver.public_key,
                    "status": "active",
                },
            )
            forged_identity["issuerGeneration"] = 1
            forged_identity["signature"] = child.sign(
                {key: value for key, value in forged_identity.items() if key != "signature"}
            )
            approval = make_recovery_approval(
                approver, "node", 1, role="operator", approver_generation=1,
            )
            authorization = make_recovery_authorization(
                self.key, "node", 1, "replacement", [approval],
            )

            outcomes = runtime.ingest([relationship, forged_identity, authorization])
            self.assertEqual([item["status"] for item in outcomes],
                             ["accepted", "quarantined", "quarantined"])
            self.assertEqual(outcomes[1]["reason"], "unauthorized-authority")
            self.assertEqual(outcomes[2]["reason"], "unknown-approver-generation")
            self.assertNotIn("approver-from-child", runtime.projection())
        finally:
            runtime.close()

    def test_lifecycle_families_require_shapes_and_recovery_provenance(self):
        identity = make_identity_generation(self.key, "node", 1, self.key.public_key)
        approval = make_recovery_approval(
            self.key, "node", 1, role="operator", approver_generation=1,
        )
        authorization = make_recovery_authorization(
            self.key, "node", 1, self.key.public_key, [approval],
            provenance=[{"source": "operator", "reason": "lost-key"}],
        )
        revoked = make_revocation(self.key, "node", 1, "lost-key")
        replacement = make_identity_generation(
            self.key, "node", 2, self.key.public_key, predecessor="node:1",
            recovery_authorization=authorization,
        )
        outcomes = self.runtime.ingest([identity, authorization, revoked, replacement])
        self.assertEqual([outcome["status"] for outcome in outcomes],
                         ["quarantined", "accepted", "accepted", "accepted"])
        self.assertEqual(outcomes[0]["reason"], "revoked-generation")
        self.assertEqual(self.runtime.projection()["node"]["generation"], 2)
        self.assertEqual(self.runtime.projection()["node"]["payload"]["provenance"],
                         [{"source": "operator", "reason": "lost-key"}])

    def test_revoked_generation_cannot_materialize_or_be_rebound_without_signed_approval(self):
        identity = make_identity_generation(self.key, "node", 1, self.key.public_key)
        revoked = make_revocation(self.key, "node", 1, "compromised")
        forged = make_identity_generation(self.key, "node", 2, self.key.public_key, predecessor="node:1")
        outcomes = self.runtime.ingest([identity, revoked, forged])
        self.assertEqual(outcomes[-1]["reason"], "missing-recovery-authorization")
        self.assertEqual(self.runtime.projection(), {})
        self.assertIn("revoked-generation", {item["reason"] for item in self.runtime.quarantine()})


class OpenBaoProviderTests(unittest.TestCase):
    def test_mock_command_materializes_atomic_0600_value_and_digest_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = root / "provider.py"
            provider.write_text(
                "import json, sys\n"
                "request = json.loads(sys.stdin.readline())\n"
                "print(json.dumps({'data': {request['field']: 'runtime-secret'}}))\n",
                encoding="utf-8",
            )
            output, ready = root / "credentials" / "db", root / "ready" / "db"
            result = subprocess.run([
                sys.executable, "-m", "arbor_registry_runtime.openbao_provider",
                "--path", "kv/data/arbor/db", "--field", "url",
                "--output", str(output), "--ready", str(ready),
                "--provider-command", sys.executable, str(provider),
            ], check=False, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(output.read_text(), "runtime-secret")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(ready.stat().st_mode), 0o644)
            self.assertNotIn("runtime-secret", ready.read_text())
            self.assertEqual(len(ready.read_text().strip()), 64)

    def test_openbao_shapes_require_string_field(self):
        self.assertEqual(_json_value({"data": {"url": "x"}}, "url"), "x")
        self.assertEqual(_json_value({"data": {"data": {"url": "x"}}}, "url"), "x")
        with self.assertRaises(ValueError):
            _json_value({"data": {"url": 1}}, "url")


if __name__ == "__main__":
    unittest.main()
