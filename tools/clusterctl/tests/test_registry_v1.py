import base64
import copy
import datetime as dt
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from clusterctl import registry
from clusterctl.announcements import (
    build_announcement,
    decode_pubsub_event,
    listen_and_trigger,
    should_trigger,
    validate_announcement,
)
from clusterctl.canonical import CanonicalJSONError, canonical_bytes
from clusterctl.events import read_json, write_json
from clusterctl.follower import fetch_and_materialize
from clusterctl.ipfs import key_names, resolve_name
from clusterctl.main import (
    build_identity_matrix,
    build_live_identity_matrices,
    same_leader_stale_burn_targets,
    write_public_identity_event,
    write_supersedence_record,
)
from clusterctl.onion import publish_mirror, validate_head
from clusterctl.registry import _atomic_write_json, canonical_event_path, finalize_event, reconcile, validate_registry
from clusterctl.signing import key_fingerprint, public_key_from_private, sign_record, verify_signature
from clusterctl.snapshot import build_snapshot, publish_snapshot
from clusterctl.status import build_status_record, validate_status_record


class RegistryV1Test(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.registry = self.root / "registry"
        self.output = self.root / "run"
        self.local_state = self.root / "local-state"
        self.keys = {}
        self.public_keys = {}
        for leader in ["leader-a", "leader-b"]:
            key = self.root / leader
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                check=True,
            )
            self.keys[leader] = key
            self.public_keys[leader] = public_key_from_private(key)
        self.policy = {
            "clusterId": "test-cluster",
            "hostName": "follower",
            "localStatePath": str(self.local_state),
            "trustedLeaders": {
                leader: {
                    "canWrite": True,
                    "publicSigningKey": public_key,
                    "ipnsName": f"k51-test-{leader}",
                }
                for leader, public_key in self.public_keys.items()
            },
            "policy": {
                "policyGeneration": 1,
                "allowPlaceholderSignatures": False,
                "requireReceiptBeforePromote": True,
                "burnedAlwaysWins": True,
                "sameGenerationConflict": "freeze-subject",
                "allowRollback": False,
                "thresholds": {
                    "hostAgeRotation": 2,
                    "leaderPolicyUpdate": 2,
                },
            },
            "registry": {
                "publisherStatePath": str(self.root / "publisher-state"),
                "followerCachePath": str(self.root / "follower-cache"),
                "acceptedRegistryPath": str(self.root / "accepted-registry"),
                "ipfs": {"keyName": "cluster-identity-leader-a"},
                "transports": {"pubsub": True},
                "pubsub": {
                    "enable": True,
                    "topic": "cluster-identity/test-cluster/roots/v1",
                    "maxHintAgeSeconds": 600,
                    "maxFutureSkewSeconds": 60,
                },
            },
        }

    def tearDown(self):
        self.temporary.cleanup()

    def test_atomic_state_write_keeps_group_writable_mode(self):
        path = self.local_state / "checkpoint.json"
        path.parent.mkdir(parents=True)
        write_json(path, {"old": True})
        path.chmod(0o600)

        _atomic_write_json(path, {"new": True})

        self.assertEqual(read_json(path), {"new": True})
        self.assertEqual(path.stat().st_mode & 0o777, 0o660)

    def write_event(
        self,
        leader: str,
        generation: int,
        address: str,
        state: str = "active",
        fingerprint: str | None = None,
        registry_path: Path | None = None,
        service: str = "yggdrasil",
        public: dict | None = None,
    ) -> Path:
        registry_path = registry_path or self.registry
        public = public or {
            "yggdrasilPublicKey": f"key-{address}",
            "yggdrasilAddress": address,
            "fingerprint": fingerprint or f"sha256:{address}",
        }
        event = {
            "schema": "cluster.identity.event.v1",
            "clusterId": "test-cluster",
            "eventId": f"{leader}-{generation}-{state}-{address}",
            "leader": leader,
            "leaderKeyId": key_fingerprint(self.public_keys[leader]),
            "policyGeneration": 1,
            "subject": {"node": "node-a", "service": service},
            "generation": generation,
            "state": state,
            "public": public,
            "privateDelivery": None,
            "supersedes": [],
            "createdAt": f"2026-06-23T00:00:{generation:02d}Z",
        }
        finalize_event(registry_path, event)
        event["signature"] = sign_record(event, self.keys[leader])
        path = canonical_event_path(registry_path, event)
        write_json(path, event)
        return path

    def write_burn(self, leader: str, generation: int, fingerprint: str) -> Path:
        event = {
            "schema": "cluster.identity.event.v1",
            "clusterId": "test-cluster",
            "eventId": f"{leader}-burn-{generation}",
            "leader": leader,
            "leaderKeyId": key_fingerprint(self.public_keys[leader]),
            "policyGeneration": 1,
            "subject": {"node": "node-a", "service": "yggdrasil"},
            "generation": generation,
            "state": "burned",
            "burned": {
                "fingerprint": fingerprint,
                "reason": "test",
                "burnedAt": "2026-06-23T00:01:00Z",
                "scope": "subject-generation",
            },
            "createdAt": "2026-06-23T00:01:00Z",
        }
        finalize_event(self.registry, event)
        event["signature"] = sign_record(event, self.keys[leader])
        path = canonical_event_path(self.registry, event)
        write_json(path, event)
        return path

    def write_rotation_intent(
        self,
        target_path: Path,
        mode: str = "graceful",
        rotation_id: str = "rotation-test",
        minimum: int = 1,
        required_nodes: list[str] | None = None,
    ) -> Path:
        target_event = read_json(target_path, {})
        subject = target_event["subject"]
        fingerprint = next(iter(registry._public_fingerprints(target_event)))
        record = {
            "schema": registry.ROTATION_SCHEMA,
            "clusterId": "test-cluster",
            "rotationId": rotation_id,
            "eventId": f"{rotation_id}-intent",
            "leader": "leader-a",
            "leaderKeyId": key_fingerprint(self.public_keys["leader-a"]),
            "policyGeneration": 1,
            "mode": mode,
            "reason": "unit test rotation",
            "trigger": {"kind": "unit-test", "hosts": [subject["node"]]},
            "targets": [
                {
                    "node": subject["node"],
                    "service": subject["service"],
                    "generation": target_event["generation"],
                    "eventHash": target_event["eventHash"],
                    "fingerprint": fingerprint,
                    "exposureReason": "unit test exposure",
                }
            ],
            "acknowledgementPolicy": {
                "minimum": minimum,
                "requiredNodes": required_nodes if required_nodes is not None else ["node-a"],
                "deadline": "2026-07-07T00:00:00Z",
            },
            "transportOrder": [],
            "createdAt": "2026-06-23T00:02:00Z",
        }
        registry.finalize_rotation(self.registry, record)
        record["signature"] = sign_record(record, self.keys["leader-a"])
        path = canonical_event_path(self.registry, record)
        write_json(path, record)
        return path

    def write_rotation_acknowledgement(
        self,
        rotation_id: str,
        replacement_event_hashes: list[str],
        node: str = "node-a",
    ) -> Path:
        record = {
            "schema": registry.ROTATION_ACK_SCHEMA,
            "clusterId": "test-cluster",
            "rotationId": rotation_id,
            "node": node,
            "replacementEventHashes": replacement_event_hashes,
            "acceptedRootCid": "bafyacceptedroot",
            "acceptedAt": "2026-06-23T00:05:00Z",
            "signedByNode": {
                "type": "ssh-host-ed25519",
                "publicKey": self.public_keys["leader-a"],
                "keyId": key_fingerprint(self.public_keys["leader-a"]),
            },
        }
        record["signature"] = sign_record(record, self.keys["leader-a"])
        path = self.registry / "receipts" / node / f"{rotation_id}.ack.json"
        write_json(path, record)
        return path

    def active_generation(self):
        state = read_json(self.output / "active.json", {})
        return state["nodes"]["node-a"]["yggdrasil"]["generation"]

    def build_follower_snapshot(
        self,
        source: Path,
        destination: Path,
        leader: str,
        previous_cid: str | None = None,
        previous_sequence: int = 0,
    ) -> None:
        policy = copy.deepcopy(self.policy)
        policy["localStatePath"] = str(self.root / f"builder-state-{destination.name}")
        publisher_state = self.root / f"builder-publisher-{destination.name}"
        policy["registry"]["publisherStatePath"] = str(publisher_state)
        if previous_cid is not None:
            write_json(
                publisher_state / f"{leader}.json",
                {"rootCid": previous_cid, "rootSequence": previous_sequence},
            )
        build_snapshot(source, destination, policy, leader, self.keys[leader])

    def fake_ipfs_fetch(self, snapshots: dict[str, Path]):
        def fetch(_policy, cid, destination):
            shutil.copytree(snapshots[cid], destination)

        return fetch

    def test_canonical_profile_is_stable_and_integer_only(self):
        self.assertEqual(canonical_bytes({"z": 1, "a": [True, None]}), b'{"a":[true,null],"z":1}')
        with self.assertRaises(CanonicalJSONError):
            canonical_bytes({"notAllowed": 1.5})

    def test_valid_hash_chain_and_signature(self):
        self.write_event("leader-a", 1, "200::1")
        self.write_event("leader-a", 2, "200::2")
        self.assertEqual(validate_registry(self.registry, self.policy), [])

    @patch(
        "clusterctl.ipfs._capture",
        return_value=(
            "k51-self self                                  \n"
            "k51-leader cluster-identity-desktoptoodle        \n"
            "k51-status cluster-identity-status-desktoptoodle "
        ),
    )
    def test_ipfs_key_names_trims_padded_kubo_columns(self, _capture):
        self.assertEqual(
            key_names(self.policy),
            {
                "self": "k51-self",
                "cluster-identity-desktoptoodle": "k51-leader",
                "cluster-identity-status-desktoptoodle": "k51-status",
            },
        )

    @patch("clusterctl.ipfs._capture", return_value="/ipfs/bafynewroot")
    def test_ipfs_resolve_name_bypasses_stale_cache(self, capture):
        self.assertEqual(resolve_name(self.policy, "k51-leader"), "bafynewroot")
        self.assertIn("--nocache", capture.call_args.args)

    def test_node_status_record_reports_materialized_services(self):
        write_json(
            self.output / "active.json",
            {
                "nodes": {
                    "node-a": {
                        "yggdrasil": {
                            "generation": 3,
                            "state": "active",
                            "public": {"yggdrasilAddress": "200::3"},
                        }
                    }
                }
            },
        )
        write_json(
            self.local_state / "checkpoint.json",
            {
                "heads": {
                    "leader-a": {
                        "cid": "bafyroot",
                        "rootSequence": 7,
                        "acceptedAt": "2026-06-23T00:00:00Z",
                    }
                }
            },
        )

        record = build_status_record(
            self.policy,
            "node-a",
            self.output,
            self.local_state,
            self.keys["leader-a"],
            "k51-status-node-a",
        )

        self.assertEqual(record["schema"], "cluster.identity.node-status.v1")
        self.assertEqual(record["statusIpnsName"], "k51-status-node-a")
        self.assertEqual(
            record["implementedServices"]["yggdrasil"]["public"]["yggdrasilAddress"],
            "200::3",
        )
        self.assertEqual(
            record["acceptedServices"]["nodes"]["node-a"]["yggdrasil"]["generation"],
            3,
        )
        self.assertEqual(
            record["acceptedRegistryHeads"]["leader-a"]["rootSequence"],
            7,
        )
        ok, reason = verify_signature(record, {})
        self.assertTrue(ok, reason)

    def test_node_status_validation_compares_signing_key_fingerprint(self):
        write_json(
            self.output / "active.json",
            {
                "nodes": {
                    "node-a": {
                        "yggdrasil": {
                            "generation": 3,
                            "state": "active",
                            "public": {"yggdrasilAddress": "200::3"},
                        }
                    }
                }
            },
        )
        policy = copy.deepcopy(self.policy)
        policy["statusPublishers"] = {
            "node-a": {
                "ipnsName": "k51-status-node-a",
                "publicSigningKey": self.public_keys["leader-a"],
            }
        }
        record = build_status_record(
            policy,
            "node-a",
            self.output,
            self.local_state,
            self.keys["leader-a"],
            "k51-status-node-a",
        )
        record.pop("signature")
        record["signedByNode"]["publicKey"] = (
            record["signedByNode"]["publicKey"] + " root@nixos"
        )
        record["signature"] = sign_record(record, self.keys["leader-a"])

        ok, reason = validate_status_record(
            policy, "node-a", record, "k51-status-node-a"
        )

        self.assertTrue(ok, reason)

    def test_materialized_ssh_config_prefers_active_yggdrasil_identity(self):
        self.write_event("leader-a", 1, "200::1")
        self.write_event(
            "leader-a",
            1,
            "ssh-host",
            service="ssh-host",
            public={
                "sshHostKey": self.public_keys["leader-a"],
                "fingerprint": "sha256:ssh-host",
            },
        )

        reconcile(self.registry, self.output, self.policy)

        self.assertEqual(
            (self.output / "ssh_config").read_text(encoding="utf-8"),
            "Host node-a node-a-ygg\n"
            "  HostName 200::1\n"
            "  HostKeyAlias node-a\n",
        )
        self.assertEqual(
            (self.output / "ssh_known_hosts").read_text(encoding="utf-8"),
            f"node-a {self.public_keys['leader-a']}\n",
        )

    def test_burning_extra_generation_does_not_tombstone_desired_lower_generation(self):
        self.write_event("leader-a", 1, "200::1", fingerprint="sha256:g1")
        self.write_event(
            "leader-a",
            2,
            "200::2",
            state="staged",
            fingerprint="sha256:g2",
        )
        self.write_burn("leader-a", 2, "sha256:g2")

        reconcile(self.registry, self.output, self.policy)

        self.assertEqual(self.active_generation(), 1)
        conflicts = read_json(self.output / "conflicts.json", {})
        self.assertNotIn("node-a/yggdrasil", conflicts.get("subjects") or {})

    def test_materialized_ssh_config_replaces_non_writable_existing_file(self):
        self.write_event("leader-a", 1, "200::1")
        ssh_config = self.output / "ssh_config"
        ssh_config.parent.mkdir(parents=True, exist_ok=True)
        ssh_config.write_text("stale\n", encoding="utf-8")
        ssh_config.chmod(0o444)
        self.addCleanup(lambda: ssh_config.chmod(0o644) if ssh_config.exists() else None)

        reconcile(self.registry, self.output, self.policy)

        self.assertEqual(
            ssh_config.read_text(encoding="utf-8"),
            "Host node-a node-a-ygg\n"
            "  HostName 200::1\n"
            "  HostKeyAlias node-a\n",
        )

    def test_conflict_keeps_last_good_and_higher_generation_repairs(self):
        self.write_event("leader-a", 1, "200::1")
        reconcile(self.registry, self.output, self.policy)
        self.assertEqual(self.active_generation(), 1)

        self.write_event("leader-a", 2, "200::2")
        self.write_event("leader-b", 2, "200::dead")
        reconcile(self.registry, self.output, self.policy)
        self.assertEqual(self.active_generation(), 1)
        conflicts = read_json(self.output / "conflicts.json", {})
        self.assertEqual(conflicts["subjects"]["node-a/yggdrasil"]["generation"], 2)

        self.write_event("leader-a", 3, "200::3")
        reconcile(self.registry, self.output, self.policy)
        self.assertEqual(self.active_generation(), 3)

    def test_signed_supersedence_resolves_same_generation_without_mutation(self):
        self.write_event("leader-a", 1, "200::1")
        reconcile(self.registry, self.output, self.policy)
        winner_path = self.write_event("leader-b", 2, "200::2")
        loser_path = self.write_event("leader-a", 2, "200::dead")
        reconcile(self.registry, self.output, self.policy)
        self.assertEqual(self.active_generation(), 1)

        winner = read_json(winner_path, {})
        loser = read_json(loser_path, {})
        resolution_path = write_supersedence_record(
            registry_path=self.registry,
            policy=self.policy,
            leader="leader-a",
            leader_key_arg=None,
            superseding_event=winner,
            superseded_event=loser,
            reason="manual test resolution",
            signing_key=self.keys["leader-a"],
        )

        self.assertIsNotNone(resolution_path)
        self.assertTrue(winner_path.exists())
        self.assertTrue(loser_path.exists())
        self.assertEqual(validate_registry(self.registry, self.policy), [])
        reconcile(self.registry, self.output, self.policy)
        active = read_json(self.output / "active.json", {})
        self.assertEqual(
            active["nodes"]["node-a"]["yggdrasil"]["public"]["yggdrasilAddress"],
            "200::2",
        )
        self.assertEqual(read_json(self.output / "conflicts.json", {})["subjects"], {})

    def test_supersedence_can_select_lower_generation_over_accepted_high_generation(self):
        winner_path = self.write_event("leader-a", 13, "200::13")
        reconcile(self.registry, self.output, self.policy)
        loser_path = self.write_event("leader-b", 99, "200::99")
        reconcile(self.registry, self.output, self.policy)
        self.assertEqual(self.active_generation(), 99)

        write_supersedence_record(
            registry_path=self.registry,
            policy=self.policy,
            leader="leader-a",
            leader_key_arg=None,
            superseding_event=read_json(winner_path, {}),
            superseded_event=read_json(loser_path, {}),
            reason="reject faulty high generation",
            signing_key=self.keys["leader-a"],
        )
        reconcile(self.registry, self.output, self.policy)

        self.assertEqual(self.active_generation(), 13)
        checkpoint = read_json(self.local_state / "checkpoint.json", {})
        self.assertEqual(checkpoint["subjects"]["node-a/yggdrasil"]["generation"], 13)

    def test_supersedence_rejects_a_guessed_or_future_target_hash(self):
        winner_path = self.write_event("leader-a", 2, "200::2")
        loser_path = self.write_event("leader-b", 2, "200::dead")
        resolution_path = write_supersedence_record(
            registry_path=self.registry,
            policy=self.policy,
            leader="leader-a",
            leader_key_arg=None,
            superseding_event=read_json(winner_path, {}),
            superseded_event=read_json(loser_path, {}),
            reason="manual resolution",
            signing_key=self.keys["leader-a"],
        )
        resolution = read_json(resolution_path, {})
        resolution["superseded"]["eventHash"] = "sha256:" + ("0" * 64)
        resolution["eventHash"] = registry.event_content_hash(resolution)
        resolution["signature"] = sign_record(resolution, self.keys["leader-a"])
        write_json(resolution_path, resolution)

        failures = validate_registry(self.registry, self.policy)
        self.assertTrue(
            any(
                "supersededEvent does not match referenced hash" in failure
                for failure in failures
            )
        )

    def test_cyclic_supersedence_freezes_at_last_good(self):
        self.write_event("leader-a", 1, "200::1")
        reconcile(self.registry, self.output, self.policy)
        event_a_path = self.write_event("leader-a", 2, "200::2")
        event_b_path = self.write_event("leader-b", 2, "200::dead")
        event_a = read_json(event_a_path, {})
        event_b = read_json(event_b_path, {})
        write_supersedence_record(
            registry_path=self.registry,
            policy=self.policy,
            leader="leader-a",
            leader_key_arg=None,
            superseding_event=event_a,
            superseded_event=event_b,
            reason="first resolution",
            signing_key=self.keys["leader-a"],
        )
        write_supersedence_record(
            registry_path=self.registry,
            policy=self.policy,
            leader="leader-b",
            leader_key_arg=None,
            superseding_event=event_b,
            superseded_event=event_a,
            reason="competing resolution",
            signing_key=self.keys["leader-b"],
        )

        reconcile(self.registry, self.output, self.policy)

        self.assertEqual(self.active_generation(), 1)
        conflict = read_json(self.output / "conflicts.json", {})["subjects"][
            "node-a/yggdrasil"
        ]
        self.assertEqual(conflict["reason"], "cyclic-supersedence")

    def test_publish_appends_supersedence_for_observed_foreign_conflict(self):
        loser_path = self.write_event("leader-b", 2, "200::dead")
        path = write_public_identity_event(
            registry_path=self.registry,
            policy=self.policy,
            leader="leader-a",
            leader_key_arg=None,
            node="node-a",
            service="yggdrasil",
            generation=2,
            state="active",
            public={
                "yggdrasilPublicKey": "key-200::2",
                "yggdrasilAddress": "200::2",
            },
            private_delivery=None,
            supersedes=[],
            signature=None,
            signing_key=self.keys["leader-a"],
            no_commit=True,
            allow_duplicate=False,
        )

        self.assertIsNotNone(path)
        resolutions = [
            record
            for _record_path, record in registry.supersedence_records(
                registry.load_events(self.registry)
            )
        ]
        self.assertEqual(len(resolutions), 1)
        self.assertEqual(
            resolutions[0]["superseded"]["eventHash"],
            read_json(loser_path, {})["eventHash"],
        )
        reconcile(self.registry, self.output, self.policy)
        active = read_json(self.output / "active.json", {})
        self.assertEqual(
            active["nodes"]["node-a"]["yggdrasil"]["public"]["yggdrasilAddress"],
            "200::2",
        )

    def test_publish_burns_old_same_leader_generation_after_rotation(self):
        self.write_event("leader-a", 1, "200::1", fingerprint="sha256:old")
        path = write_public_identity_event(
            registry_path=self.registry,
            policy=self.policy,
            leader="leader-a",
            leader_key_arg=None,
            node="node-a",
            service="yggdrasil",
            generation=2,
            state="active",
            public={
                "yggdrasilPublicKey": "key-200::2",
                "yggdrasilAddress": "200::2",
                "fingerprint": "sha256:new",
            },
            private_delivery=None,
            supersedes=[],
            signature=None,
            signing_key=self.keys["leader-a"],
            no_commit=True,
            allow_duplicate=False,
            burn_same_leader_previous=True,
        )

        self.assertIsNotNone(path)
        burns = [
            event
            for _event_path, event in registry.identity_events(
                registry.load_events(self.registry)
            )
            if event.get("state") == "burned"
        ]
        self.assertEqual(len(burns), 1)
        self.assertEqual(burns[0]["generation"], 1)
        self.assertEqual(burns[0]["burned"]["fingerprint"], "sha256:old")

        reconcile(self.registry, self.output, self.policy)
        self.assertEqual(self.active_generation(), 2)

    def test_publish_does_not_burn_same_payload_duplicate(self):
        self.write_event("leader-a", 1, "200::1", fingerprint="sha256:same")
        path = write_public_identity_event(
            registry_path=self.registry,
            policy=self.policy,
            leader="leader-a",
            leader_key_arg=None,
            node="node-a",
            service="yggdrasil",
            generation=2,
            state="active",
            public={
                "yggdrasilPublicKey": "key-200::1",
                "yggdrasilAddress": "200::1",
                "fingerprint": "sha256:same",
            },
            private_delivery=None,
            supersedes=[],
            signature=None,
            signing_key=self.keys["leader-a"],
            no_commit=True,
            allow_duplicate=False,
            burn_same_leader_previous=True,
        )

        self.assertIsNotNone(path)
        burns = [
            event
            for _event_path, event in registry.identity_events(
                registry.load_events(self.registry)
            )
            if event.get("state") == "burned"
        ]
        self.assertEqual(burns, [])

    def test_live_matrix_burn_suppresses_same_generation_active_claim(self):
        records = {
            "node-a": {
                "yggdrasil": [
                    {
                        "generation": 1,
                        "state": "active",
                        "leader": "leader-a",
                    },
                    {
                        "generation": 2,
                        "state": "active",
                        "leader": "leader-a",
                    },
                    {
                        "generation": 2,
                        "state": "burned",
                        "leader": "leader-a",
                    },
                ]
            }
        }

        matrices = build_live_identity_matrices(["node-a"], records)

        cell = matrices[0]["rows"][0]["nodes"]["node-a"]["cell"]
        self.assertEqual(cell, "g1/a,g2/b")
        self.assertEqual(
            [
                record["state"]
                for record in matrices[0]["rows"][0]["nodes"]["node-a"]["records"]
            ],
            ["active", "burned"],
        )

    def test_live_matrix_limits_burned_records_by_default(self):
        records = {
            "node-a": {
                "yggdrasil": [
                    {
                        "generation": generation,
                        "state": "burned",
                        "leader": "leader-a",
                        "createdAt": f"2026-06-23T00:00:0{generation}Z",
                    }
                    for generation in [1, 2, 3]
                ]
            }
        }

        matrices = build_live_identity_matrices(["node-a"], records)

        self.assertEqual(
            matrices[0]["rows"][0]["nodes"]["node-a"]["cell"],
            "g2/b,g3/b",
        )

    def test_live_matrix_can_hide_burned_records(self):
        records = {
            "node-a": {
                "yggdrasil": [
                    {
                        "generation": 1,
                        "state": "active",
                        "leader": "leader-a",
                    },
                    {
                        "generation": 2,
                        "state": "burned",
                        "leader": "leader-a",
                    },
                ]
            }
        }

        matrices = build_live_identity_matrices(["node-a"], records, burn_limit=0)

        self.assertEqual(
            matrices[0]["rows"][0]["nodes"]["node-a"]["cell"],
            "g1/a",
        )

    def test_identity_matrix_marks_active_from_target_status(self):
        inventory = {
            "hosts": {"node-a": {}, "node-b": {}},
            "identityRequirements": {
                "byHost": {"node-a": {"yggdrasil": {}}, "node-b": {}}
            },
            "identities": {
                "services": {
                    "yggdrasil": {
                        "node-a": {
                            "generation": 1,
                            "state": "active",
                            "public": {
                                "yggdrasilAddress": "200::1",
                            },
                        }
                    }
                }
            },
        }
        status_records = {
            "node-a": {
                "implementedServices": {
                    "yggdrasil": {
                        "generation": 1,
                        "state": "active",
                        "public": {
                            "yggdrasilAddress": "200::1",
                        },
                    }
                }
            }
        }

        report = build_identity_matrix(inventory, status_records=status_records)

        self.assertEqual(
            report["rows"][0]["nodes"]["node-a"]["cell"],
            "g1/a",
        )

    def test_identity_matrix_marks_acknowledged_active_from_peer_status(self):
        inventory = {
            "hosts": {"node-a": {}, "node-b": {}},
            "identityRequirements": {
                "byHost": {"node-a": {"yggdrasil": {}}, "node-b": {}}
            },
            "identities": {
                "services": {
                    "yggdrasil": {
                        "node-a": {
                            "generation": 1,
                            "state": "active",
                            "public": {
                                "yggdrasilAddress": "200::1",
                            },
                        }
                    }
                }
            },
        }
        service_record = {
            "generation": 1,
            "state": "active",
            "public": {
                "yggdrasilAddress": "200::1",
            },
        }
        status_records = {
            "node-a": {"implementedServices": {"yggdrasil": service_record}},
            "node-b": {
                "acceptedServices": {
                    "nodes": {
                        "node-a": {"yggdrasil": service_record},
                    }
                }
            },
        }

        report = build_identity_matrix(inventory, status_records=status_records)

        self.assertEqual(
            report["rows"][0]["nodes"]["node-a"]["cell"],
            "g1/aa",
        )

    def test_identity_matrix_marks_ledger_active_unconfirmed_without_target_status(self):
        inventory = {
            "hosts": {"node-a": {}},
            "identityRequirements": {"byHost": {"node-a": {"yggdrasil": {}}}},
            "identities": {
                "services": {
                    "yggdrasil": {
                        "node-a": {
                            "generation": 1,
                            "state": "active",
                            "public": {
                                "yggdrasilAddress": "200::1",
                            },
                        }
                    }
                }
            },
        }

        report = build_identity_matrix(inventory, status_records={})

        self.assertEqual(
            report["rows"][0]["nodes"]["node-a"]["cell"],
            "g1/au",
        )

    def test_stale_burn_targets_skip_guarded_services_by_default(self):
        self.write_event("leader-a", 1, "200::1", fingerprint="sha256:ygg")
        self.write_event(
            "leader-a",
            1,
            "ssh-host",
            service="ssh-host",
            public={
                "sshHostKey": self.public_keys["leader-a"],
                "fingerprint": "sha256:ssh-host",
            },
        )

        default_targets = same_leader_stale_burn_targets(
            registry_path=self.registry,
            observed_registry_path=None,
            leader="leader-a",
            desired={},
            include_guarded=False,
        )
        guarded_targets = same_leader_stale_burn_targets(
            registry_path=self.registry,
            observed_registry_path=None,
            leader="leader-a",
            desired={},
            include_guarded=True,
        )

        self.assertEqual(
            [
                (
                    target[0]["subject"]["service"],
                    target[0]["public"]["fingerprint"],
                )
                for target in default_targets
            ],
            [("yggdrasil", "sha256:ygg")],
        )
        self.assertEqual(
            sorted(
                (
                    target[0]["subject"]["service"],
                    target[0]["public"]["fingerprint"],
                )
                for target in guarded_targets
            ),
            [("ssh-host", "sha256:ssh-host"), ("yggdrasil", "sha256:ygg")],
        )

    def test_stale_burn_targets_include_newer_generation_not_in_inventory(self):
        self.write_event("leader-a", 2, "200::2", fingerprint="sha256:new")

        targets = same_leader_stale_burn_targets(
            registry_path=self.registry,
            observed_registry_path=None,
            leader="leader-a",
            desired={
                ("node-a", "yggdrasil"): {
                    "generation": 1,
                    "public": {"fingerprint": "sha256:old"},
                }
            },
            include_guarded=False,
        )

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0][0]["generation"], 2)
        self.assertEqual(
            targets[0][1],
            "publishing leader inventory does not imply this newer generation",
        )

    def test_stale_burn_targets_skip_guarded_mismatch_by_default(self):
        self.write_event(
            "leader-a",
            2,
            "ssh-host",
            service="ssh-host",
            public={
                "sshHostKey": self.public_keys["leader-b"],
                "fingerprint": "sha256:new-ssh",
            },
        )
        desired = {
            ("node-a", "ssh-host"): {
                "generation": 1,
                "public": {
                    "sshHostKey": self.public_keys["leader-a"],
                    "fingerprint": "sha256:old-ssh",
                },
            }
        }

        default_targets = same_leader_stale_burn_targets(
            registry_path=self.registry,
            observed_registry_path=None,
            leader="leader-a",
            desired=desired,
            include_guarded=False,
        )
        guarded_targets = same_leader_stale_burn_targets(
            registry_path=self.registry,
            observed_registry_path=None,
            leader="leader-a",
            desired=desired,
            include_guarded=True,
        )

        self.assertEqual(default_targets, [])
        self.assertEqual(len(guarded_targets), 1)
        self.assertEqual(guarded_targets[0][0]["subject"]["service"], "ssh-host")

    def test_supersedence_with_signed_embedded_foreign_event_survives_snapshot_merge(self):
        leader_a_registry = self.root / "leader-a-registry"
        leader_b_registry = self.root / "leader-b-registry"
        winner_path = self.write_event(
            "leader-a", 2, "200::2", registry_path=leader_a_registry
        )
        loser_path = self.write_event(
            "leader-b", 2, "200::dead", registry_path=leader_b_registry
        )
        write_supersedence_record(
            registry_path=leader_a_registry,
            policy=self.policy,
            leader="leader-a",
            leader_key_arg=None,
            superseding_event=read_json(winner_path, {}),
            superseded_event=read_json(loser_path, {}),
            reason="manual cross-head resolution",
            signing_key=self.keys["leader-a"],
        )
        leader_a_snapshot = self.root / "resolved-head-a"
        leader_b_snapshot = self.root / "resolved-head-b"
        self.build_follower_snapshot(
            leader_a_registry, leader_a_snapshot, "leader-a"
        )
        self.build_follower_snapshot(
            leader_b_registry, leader_b_snapshot, "leader-b"
        )
        snapshots = {
            "bafyresolveda": leader_a_snapshot,
            "bafyresolvedb": leader_b_snapshot,
        }
        resolved = {
            "k51-test-leader-a": "bafyresolveda",
            "k51-test-leader-b": "bafyresolvedb",
        }

        with patch(
            "clusterctl.follower.ipfs.resolve_name",
            side_effect=lambda _policy, name: resolved[name],
        ), patch(
            "clusterctl.follower.ipfs.fetch_directory",
            side_effect=self.fake_ipfs_fetch(snapshots),
        ), patch("clusterctl.follower.ipfs.pin"), patch(
            "clusterctl.follower.apply_mod.apply_materialized"
        ):
            fetch_and_materialize(self.policy, self.output)

        active = read_json(self.output / "active.json", {})
        self.assertEqual(
            active["nodes"]["node-a"]["yggdrasil"]["public"]["yggdrasilAddress"],
            "200::2",
        )

    def test_missing_old_snapshot_cannot_roll_back_last_good(self):
        path = self.write_event("leader-a", 1, "200::1")
        reconcile(self.registry, self.output, self.policy)
        path.unlink()
        reconcile(self.registry, self.output, self.policy)
        self.assertEqual(self.active_generation(), 1)

    def test_burn_removes_active_subject_and_persists_fingerprint(self):
        fingerprint = "sha256:old"
        self.write_event("leader-a", 1, "200::1", fingerprint=fingerprint)
        reconcile(self.registry, self.output, self.policy)
        self.write_burn("leader-a", 1, fingerprint)
        reconcile(self.registry, self.output, self.policy)
        active = read_json(self.output / "active.json", {})
        burned = read_json(self.output / "burned.json", {})
        checkpoint = read_json(self.local_state / "checkpoint.json", {})
        self.assertNotIn("node-a", active["nodes"])
        self.assertEqual(burned["nodes"]["node-a"]["yggdrasil"]["state"], "burned")
        self.assertIn(fingerprint, checkpoint["burnedFingerprints"])

    def test_higher_generation_with_new_fingerprint_recovers_after_burn(self):
        old_fingerprint = "sha256:old"
        self.write_event("leader-a", 1, "200::1", fingerprint=old_fingerprint)
        self.write_burn("leader-a", 1, old_fingerprint)
        self.write_event("leader-a", 2, "200::2", fingerprint="sha256:new")
        reconcile(self.registry, self.output, self.policy)
        self.assertEqual(self.active_generation(), 2)
        burned = read_json(self.output / "burned.json", {})
        self.assertEqual(burned["nodes"]["node-a"]["yggdrasil"]["generation"], 1)

    def test_rotation_intent_materializes_pending_without_identity_selection(self):
        target_path = self.write_event("leader-a", 1, "200::1", fingerprint="sha256:old")
        self.write_rotation_intent(target_path)

        reconcile(self.registry, self.output, self.policy)

        self.assertEqual(self.active_generation(), 1)
        rotations = read_json(self.output / "rotations.json", {})
        rotation = rotations["rotations"]["rotation-test"]
        self.assertEqual(rotation["status"], "replacement-pending")
        self.assertEqual(rotation["targets"][0]["eventHash"], read_json(target_path, {})["eventHash"])

    def test_rotation_rejects_unknown_target_hash(self):
        target_path = self.write_event("leader-a", 1, "200::1", fingerprint="sha256:old")
        rotation_path = self.write_rotation_intent(target_path)
        rotation = read_json(rotation_path, {})
        rotation["targets"][0]["eventHash"] = "sha256:" + ("0" * 64)
        rotation["eventHash"] = registry.event_content_hash(rotation)
        rotation["signature"] = sign_record(rotation, self.keys["leader-a"])
        write_json(rotation_path, rotation)

        failures = validate_registry(self.registry, self.policy)

        self.assertTrue(
            any("references an unknown identity event" in failure for failure in failures)
        )

    def test_rotation_acknowledgement_makes_active_replacement_ready_to_retire(self):
        target_path = self.write_event("leader-a", 1, "200::1", fingerprint="sha256:old")
        self.write_event(
            "leader-a",
            1,
            "ssh-host",
            service="ssh-host",
            public={
                "sshHostKey": self.public_keys["leader-a"],
                "fingerprint": "sha256:ssh-host",
            },
        )
        self.write_rotation_intent(target_path)
        replacement_path = self.write_event("leader-a", 2, "200::2", fingerprint="sha256:new")
        self.write_rotation_acknowledgement(
            "rotation-test",
            [read_json(replacement_path, {})["eventHash"]],
        )

        reconcile(self.registry, self.output, self.policy)

        rotations = read_json(self.output / "rotations.json", {})
        rotation = rotations["rotations"]["rotation-test"]
        self.assertEqual(rotation["status"], "ready-to-retire")
        self.assertEqual(rotation["targets"][0]["acknowledgement"]["acknowledgedNodes"], ["node-a"])
        status = build_status_record(
            self.policy,
            "node-a",
            self.output,
            self.local_state,
            self.keys["leader-a"],
            "k51-status-node-a",
        )
        self.assertEqual(status["rotations"]["rotation-test"]["status"], "ready-to-retire")

    def test_targeted_secret_rotation_only_tracks_matching_service_replacement(self):
        self.write_event(
            "leader-a",
            1,
            "ssh-host",
            service="ssh-host",
            public={
                "sshHostKey": self.public_keys["leader-a"],
                "fingerprint": "sha256:ssh-host",
            },
        )
        target_path = self.write_event(
            "leader-a",
            1,
            "status-ipns",
            service="status-ipns",
            public={
                "ipnsName": "k51-status-old",
                "publicKey": "status-public-old",
            },
        )
        unrelated_path = self.write_event("leader-a", 2, "200::2", fingerprint="sha256:ygg-new")
        replacement_path = self.write_event(
            "leader-a",
            2,
            "status-ipns",
            service="status-ipns",
            public={
                "ipnsName": "k51-status-new",
                "publicKey": "status-public-new",
            },
        )
        self.write_rotation_intent(
            target_path,
            rotation_id="rotation-status-ipns-secret",
        )
        self.write_rotation_acknowledgement(
            "rotation-status-ipns-secret",
            [read_json(replacement_path, {})["eventHash"]],
        )

        reconcile(self.registry, self.output, self.policy)

        rotation = read_json(self.output / "rotations.json", {})["rotations"][
            "rotation-status-ipns-secret"
        ]
        target = rotation["targets"][0]
        self.assertEqual(rotation["status"], "ready-to-retire")
        self.assertEqual(target["service"], "status-ipns")
        self.assertEqual(
            target["activeReplacementEventHashes"],
            [read_json(replacement_path, {})["eventHash"]],
        )
        self.assertNotIn(
            read_json(unrelated_path, {})["eventHash"],
            target["replacementEventHashes"],
        )

    def test_emergency_burn_without_replacement_is_incomplete(self):
        target_path = self.write_event("leader-a", 1, "200::1", fingerprint="sha256:old")
        self.write_rotation_intent(
            target_path,
            mode="emergency",
            minimum=0,
            required_nodes=[],
        )
        self.write_burn("leader-a", 1, "sha256:old")

        reconcile(self.registry, self.output, self.policy)

        rotations = read_json(self.output / "rotations.json", {})
        self.assertEqual(
            rotations["rotations"]["rotation-test"]["status"],
            "emergency-incomplete",
        )

    def test_snapshot_is_signed_and_exhaustively_indexed(self):
        self.write_event("leader-a", 1, "200::1")
        snapshot_dir = self.root / "snapshot"
        root = build_snapshot(
            self.registry,
            snapshot_dir,
            self.policy,
            "leader-a",
            self.keys["leader-a"],
        )
        self.assertEqual(root["rootSequence"], 1)
        self.assertIsNone(root["previousRootCid"])
        self.assertEqual(validate_registry(snapshot_dir, self.policy), [])

        write_json(snapshot_dir / "state" / "unindexed.json", {"unexpected": True})
        failures = validate_registry(snapshot_dir, self.policy)
        self.assertTrue(any("unindexed snapshot object state/unindexed.json" in item for item in failures))

    @patch("clusterctl.snapshot.ipfs.publish_name", return_value="Published to test")
    @patch("clusterctl.snapshot.ipfs.pin")
    @patch("clusterctl.snapshot.ipfs.add_directory", side_effect=["bafyrootone", "bafydroottwo"])
    @patch(
        "clusterctl.snapshot.announcements.publish_announcement",
        return_value={"status": "published"},
    )
    def test_publish_sequences_roots_and_records_previous_cid(
        self,
        publish_announcement,
        add_directory,
        pin,
        publish_name,
    ):
        self.write_event("leader-a", 1, "200::1")
        snapshot_dir = self.root / "snapshot"
        first = publish_snapshot(
            self.registry,
            snapshot_dir,
            self.policy,
            "leader-a",
            self.keys["leader-a"],
        )
        second = publish_snapshot(
            self.registry,
            snapshot_dir,
            self.policy,
            "leader-a",
            self.keys["leader-a"],
        )

        self.assertEqual(first["rootSequence"], 1)
        self.assertEqual(second["rootSequence"], 2)
        self.assertEqual(second["previousRootCid"], "bafyrootone")
        self.assertEqual(read_json(snapshot_dir / "root.json", {})["previousRootCid"], "bafyrootone")
        self.assertEqual(add_directory.call_count, 2)
        pin.assert_called_with(self.policy, "bafydroottwo")
        publish_name.assert_called_with(
            self.policy,
            "cluster-identity-leader-a",
            "k51-test-leader-a",
            "bafydroottwo",
        )
        self.assertEqual(publish_announcement.call_count, 2)

    @patch("clusterctl.snapshot.ipfs.publish_name", side_effect=RuntimeError("IPNS unavailable"))
    @patch("clusterctl.snapshot.ipfs.pin")
    @patch("clusterctl.snapshot.ipfs.add_directory", return_value="bafyrootone")
    def test_failed_ipns_publish_does_not_advance_publisher_state(self, _add, _pin, _publish):
        self.write_event("leader-a", 1, "200::1")
        with self.assertRaisesRegex(RuntimeError, "IPNS unavailable"):
            publish_snapshot(
                self.registry,
                self.root / "snapshot",
                self.policy,
                "leader-a",
                self.keys["leader-a"],
            )
        self.assertFalse((self.root / "publisher-state" / "leader-a.json").exists())

    def test_signed_pubsub_announcement_triggers_normal_fetch(self):
        self.write_event("leader-a", 1, "200::1")
        root = build_snapshot(
            self.registry,
            self.root / "announcement-snapshot",
            self.policy,
            "leader-a",
            self.keys["leader-a"],
        )
        state = {
            "publisher": "leader-a",
            "rootCid": "bafyannouncement",
            "rootSequence": root["rootSequence"],
            "previousRootCid": root["previousRootCid"],
            "ipnsName": "k51-test-leader-a",
        }
        announcement = build_announcement(
            self.policy,
            state,
            root,
            self.keys["leader-a"],
        )
        validated = validate_announcement(self.policy, announcement)
        trigger, reason = should_trigger(self.policy, validated, {"heads": {}})

        self.assertTrue(trigger)
        self.assertEqual(reason, "fetch-required")
        self.assertEqual(validated["rootCid"], "bafyannouncement")

    def test_pubsub_announcement_rejects_tampering_and_stale_replay(self):
        self.write_event("leader-a", 1, "200::1")
        root = build_snapshot(
            self.registry,
            self.root / "announcement-snapshot",
            self.policy,
            "leader-a",
            self.keys["leader-a"],
        )
        state = {
            "publisher": "leader-a",
            "rootCid": "bafyannouncement",
            "rootSequence": root["rootSequence"],
            "previousRootCid": root["previousRootCid"],
            "ipnsName": "k51-test-leader-a",
        }
        announcement = build_announcement(
            self.policy,
            state,
            root,
            self.keys["leader-a"],
        )
        tampered = copy.deepcopy(announcement)
        tampered["rootCid"] = "bafytampered"
        with self.assertRaisesRegex(ValueError, "signature rejected"):
            validate_announcement(self.policy, tampered)

        created = dt.datetime.fromisoformat(announcement["createdAt"].replace("Z", "+00:00"))
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_announcement(
                self.policy,
                announcement,
                current_time=created + dt.timedelta(seconds=601),
            )

    def test_onion_mirror_publishes_signed_head_and_immutable_snapshot(self):
        self.policy["registry"]["transports"]["onionMirrors"] = True
        self.policy["registry"]["onion"] = {
            "mirrorPath": str(self.root / "onion-mirror"),
        }
        self.policy["trustedLeaders"]["leader-a"]["onionMirror"] = (
            f"http://{'a' * 56}.onion"
        )
        self.write_event("leader-a", 1, "200::1")
        snapshot_dir = self.root / "onion-snapshot"
        root = build_snapshot(
            self.registry,
            snapshot_dir,
            self.policy,
            "leader-a",
            self.keys["leader-a"],
        )
        state = {
            "publisher": "leader-a",
            "rootCid": "bafyonionone",
            "rootSequence": root["rootSequence"],
            "previousRootCid": root["previousRootCid"],
        }

        result = publish_mirror(
            self.policy,
            state,
            root,
            snapshot_dir,
            self.keys["leader-a"],
        )

        self.assertEqual(result["status"], "published")
        mirror = self.root / "onion-mirror"
        self.assertTrue(
            (mirror / "ipfs" / "bafyonionone" / "root.json").is_file()
        )
        head_path = mirror / "heads" / "leader-a.json"
        head = validate_head(
            self.policy,
            "leader-a",
            read_json(head_path, {}),
        )
        self.assertEqual(head["rootCid"], "bafyonionone")

        tampered = copy.deepcopy(head)
        tampered["rootCid"] = "bafytampered"
        with self.assertRaisesRegex(ValueError, "signature rejected"):
            validate_head(self.policy, "leader-a", tampered)

    def test_pubsub_hint_for_accepted_head_is_ignored(self):
        announcement = {
            "leader": "leader-a",
            "rootCid": "bafyaccepted",
            "rootSequence": 3,
        }
        trigger, reason = should_trigger(
            self.policy,
            announcement,
            {
                "heads": {
                    "leader-a": {
                        "cid": "bafyaccepted",
                        "rootSequence": 3,
                    }
                }
            },
        )
        self.assertFalse(trigger)
        self.assertEqual(reason, "already-accepted")

    def test_pubsub_listener_triggers_existing_fetch_unit(self):
        self.write_event("leader-a", 1, "200::1")
        root = build_snapshot(
            self.registry,
            self.root / "listener-snapshot",
            self.policy,
            "leader-a",
            self.keys["leader-a"],
        )
        announcement = build_announcement(
            self.policy,
            {
                "publisher": "leader-a",
                "rootCid": "bafylistener",
                "rootSequence": root["rootSequence"],
                "previousRootCid": root["previousRootCid"],
                "ipnsName": "k51-test-leader-a",
            },
            root,
            self.keys["leader-a"],
        )

        encoded = base64.urlsafe_b64encode(canonical_bytes(announcement)).rstrip(b"=")
        event = {"data": "u" + encoded.decode("ascii")}

        class FakeSubscription:
            stdout = [json.dumps(event) + "\n"]

            @staticmethod
            def wait():
                return 0

        run_command = Mock()
        with patch(
            "clusterctl.announcements.ipfs.subscribe_pubsub",
            return_value=FakeSubscription(),
        ):
            listen_and_trigger(
                self.policy,
                "cluster-identity-fetch.service",
                run_command=run_command,
                reconnect=False,
            )

        run_command.assert_called_once_with(
            [
                "systemctl",
                "start",
                "--no-block",
                "cluster-identity-fetch.service",
            ],
            check=True,
        )
        status = read_json(self.local_state / "pubsub-status.json", {})
        self.assertEqual(status["accepted"], 1)
        self.assertEqual(status["lastResult"], "fetch-triggered")

    def test_pubsub_event_decoder_rejects_oversized_payload(self):
        encoded = base64.urlsafe_b64encode(b'{}').rstrip(b"=").decode("ascii")
        self.assertEqual(decode_pubsub_event(json.dumps({"data": "u" + encoded}), 2), {})
        with self.assertRaisesRegex(ValueError, "size limit"):
            decode_pubsub_event(json.dumps({"data": "u" + encoded}), 1)

    def test_pubsub_listener_reconnects_when_kubo_restarts(self):
        class FailedSubscription:
            stdout = []

            @staticmethod
            def wait():
                return 1

        class ReplacementSubscription:
            stdout = []

            @staticmethod
            def wait():
                return 0

        delay = Mock()
        with patch(
            "clusterctl.announcements.ipfs.subscribe_pubsub",
            side_effect=[FailedSubscription(), ReplacementSubscription()],
        ) as subscribe:
            listen_and_trigger(
                self.policy,
                "cluster-identity-fetch.service",
                reconnect=True,
                sleep=delay,
                max_subscriptions=2,
            )

        self.assertEqual(subscribe.call_count, 2)
        delay.assert_called_once_with(5)
        status = read_json(self.local_state / "pubsub-status.json", {})
        self.assertEqual(status["connectionState"], "retrying")

    @patch("clusterctl.follower.apply_mod.apply_materialized")
    @patch("clusterctl.follower.ipfs.pin")
    def test_follower_accepts_ipns_head_pins_and_materializes(self, pin, _apply):
        self.policy["trustedLeaders"]["leader-b"]["ipnsName"] = None
        self.write_event("leader-a", 1, "200::1")
        snapshot_dir = self.root / "head-one"
        self.build_follower_snapshot(self.registry, snapshot_dir, "leader-a")

        with patch("clusterctl.follower.ipfs.resolve_name", return_value="bafyheadone"), patch(
            "clusterctl.follower.ipfs.fetch_directory",
            side_effect=self.fake_ipfs_fetch({"bafyheadone": snapshot_dir}),
        ):
            report = fetch_and_materialize(self.policy, self.output)

        self.assertTrue(report["materialized"])
        self.assertEqual(self.active_generation(), 1)
        checkpoint = read_json(self.local_state / "checkpoint.json", {})
        self.assertEqual(checkpoint["heads"]["leader-a"]["cid"], "bafyheadone")
        self.assertIn("bafyheadone", checkpoint["acceptedCids"])
        pin.assert_called_with(self.policy, "bafyheadone")

    @patch("clusterctl.follower.apply_mod.apply_materialized")
    @patch("clusterctl.follower.ipfs.pin")
    def test_follower_rejects_truncated_leader_event_chain(self, _pin, _apply):
        self.policy["trustedLeaders"]["leader-b"]["ipnsName"] = None
        first_path = self.write_event("leader-a", 1, "200::1")
        self.write_event("leader-a", 2, "200::2")
        first_snapshot = self.root / "event-chain-one"
        self.build_follower_snapshot(self.registry, first_snapshot, "leader-a")

        truncated_registry = self.root / "truncated-registry"
        truncated_path = (
            truncated_registry / "events" / "leader-a" / first_path.name
        )
        truncated_path.parent.mkdir(parents=True)
        shutil.copyfile(first_path, truncated_path)
        truncated_snapshot = self.root / "event-chain-two"
        self.build_follower_snapshot(
            truncated_registry,
            truncated_snapshot,
            "leader-a",
            previous_cid="bafyeventone",
            previous_sequence=1,
        )
        snapshots = {
            "bafyeventone": first_snapshot,
            "bafyeventtwo": truncated_snapshot,
        }

        with patch(
            "clusterctl.follower.ipfs.resolve_name",
            return_value="bafyeventone",
        ), patch(
            "clusterctl.follower.ipfs.fetch_directory",
            side_effect=self.fake_ipfs_fetch(snapshots),
        ):
            fetch_and_materialize(self.policy, self.output)
        with patch(
            "clusterctl.follower.ipfs.resolve_name",
            return_value="bafyeventtwo",
        ), patch(
            "clusterctl.follower.ipfs.fetch_directory",
            side_effect=self.fake_ipfs_fetch(snapshots),
        ):
            report = fetch_and_materialize(self.policy, self.output)

        self.assertEqual(self.active_generation(), 2)
        self.assertIn(
            "leader-event-chain-rollback",
            report["leaders"]["leader-a"]["reason"],
        )
        self.assertEqual(
            report["leaders"]["leader-a"]["retainedCid"], "bafyeventone"
        )

    @patch("clusterctl.follower.apply_mod.apply_materialized")
    @patch(
        "clusterctl.follower.ipfs.pin",
        side_effect=RuntimeError("IPFS unavailable"),
    )
    def test_follower_accepts_verified_onion_fallback(
        self,
        _pin,
        _apply,
    ):
        self.policy["trustedLeaders"]["leader-b"]["ipnsName"] = None
        self.policy["registry"]["transports"]["onionMirrors"] = True
        self.policy["trustedLeaders"]["leader-a"]["onionMirror"] = (
            f"http://{'a' * 56}.onion"
        )
        self.write_event("leader-a", 1, "200::1")
        snapshot_dir = self.root / "onion-head"
        self.build_follower_snapshot(
            self.registry,
            snapshot_dir,
            "leader-a",
        )
        root = read_json(snapshot_dir / "root.json", {})
        mirror_root = self.root / "onion-published"
        onion_policy = copy.deepcopy(self.policy)
        onion_policy["registry"]["onion"] = {
            "mirrorPath": str(mirror_root),
        }
        publish_mirror(
            onion_policy,
            {
                "publisher": "leader-a",
                "rootCid": "bafyonionhead",
                "rootSequence": root["rootSequence"],
                "previousRootCid": root["previousRootCid"],
            },
            root,
            snapshot_dir,
            self.keys["leader-a"],
        )
        head = read_json(
            mirror_root / "heads" / "leader-a.json",
            {},
        )

        def fetch_onion(_policy, _leader, _cid, destination):
            shutil.copytree(snapshot_dir, destination)

        with patch(
            "clusterctl.follower.ipfs.resolve_name",
            side_effect=RuntimeError("IPNS unavailable"),
        ), patch(
            "clusterctl.follower.ipfs.fetch_directory",
            side_effect=RuntimeError("IPFS unavailable"),
        ), patch(
            "clusterctl.follower.onion.fetch_head",
            return_value=validate_head(self.policy, "leader-a", head),
        ), patch(
            "clusterctl.follower.onion.fetch_snapshot",
            side_effect=fetch_onion,
        ):
            report = fetch_and_materialize(self.policy, self.output)

        self.assertTrue(report["materialized"])
        self.assertEqual(self.active_generation(), 1)
        leader = report["leaders"]["leader-a"]
        self.assertEqual(leader["transport"], "onion")
        self.assertIn("IPFS unavailable", leader["pinError"])

    @patch("clusterctl.follower.apply_mod.apply_materialized")
    @patch("clusterctl.follower.ipfs.pin")
    def test_follower_rejects_same_sequence_equivocation_and_keeps_last_good(self, _pin, _apply):
        self.policy["trustedLeaders"]["leader-b"]["ipnsName"] = None
        self.write_event("leader-a", 1, "200::1")
        first_snapshot = self.root / "head-one"
        self.build_follower_snapshot(self.registry, first_snapshot, "leader-a")

        fork_registry = self.root / "fork-registry"
        self.write_event("leader-a", 2, "200::dead", registry_path=fork_registry)
        fork_snapshot = self.root / "head-fork"
        self.build_follower_snapshot(fork_registry, fork_snapshot, "leader-a")

        snapshots = {"bafyheadone": first_snapshot, "bafyheadfork": fork_snapshot}
        with patch("clusterctl.follower.ipfs.resolve_name", return_value="bafyheadone"), patch(
            "clusterctl.follower.ipfs.fetch_directory", side_effect=self.fake_ipfs_fetch(snapshots)
        ):
            fetch_and_materialize(self.policy, self.output)
        with patch("clusterctl.follower.ipfs.resolve_name", return_value="bafyheadfork"), patch(
            "clusterctl.follower.ipfs.fetch_directory", side_effect=self.fake_ipfs_fetch(snapshots)
        ):
            report = fetch_and_materialize(self.policy, self.output)

        self.assertEqual(self.active_generation(), 1)
        self.assertIn("same-sequence-equivocation", report["leaders"]["leader-a"]["reason"])
        checkpoint = read_json(self.local_state / "checkpoint.json", {})
        self.assertEqual(checkpoint["heads"]["leader-a"]["cid"], "bafyheadone")

    @patch("clusterctl.follower.apply_mod.apply_materialized")
    @patch("clusterctl.follower.ipfs.pin")
    def test_follower_accepts_newer_root_descending_from_checkpoint(self, _pin, _apply):
        self.policy["trustedLeaders"]["leader-b"]["ipnsName"] = None
        self.write_event("leader-a", 1, "200::1")
        first_snapshot = self.root / "head-one"
        self.build_follower_snapshot(self.registry, first_snapshot, "leader-a")
        self.write_event("leader-a", 2, "200::2")
        second_snapshot = self.root / "head-two"
        self.build_follower_snapshot(
            self.registry,
            second_snapshot,
            "leader-a",
            previous_cid="bafyheadone",
            previous_sequence=1,
        )

        snapshots = {"bafyheadone": first_snapshot, "bafyheadtwo": second_snapshot}
        with patch("clusterctl.follower.ipfs.resolve_name", return_value="bafyheadone"), patch(
            "clusterctl.follower.ipfs.fetch_directory", side_effect=self.fake_ipfs_fetch(snapshots)
        ):
            fetch_and_materialize(self.policy, self.output)
        with patch("clusterctl.follower.ipfs.resolve_name", return_value="bafyheadtwo"), patch(
            "clusterctl.follower.ipfs.fetch_directory", side_effect=self.fake_ipfs_fetch(snapshots)
        ):
            report = fetch_and_materialize(self.policy, self.output)

        self.assertEqual(self.active_generation(), 2)
        self.assertEqual(report["leaders"]["leader-a"]["reason"], "newer-descendant")

    @patch("clusterctl.follower.apply_mod.apply_materialized")
    @patch("clusterctl.follower.ipfs.pin")
    def test_follower_freezes_conflicting_generation_from_two_ipns_heads(self, _pin, _apply):
        self.policy["trustedLeaders"]["leader-b"]["ipnsName"] = None
        self.write_event("leader-a", 1, "200::1")
        first_snapshot = self.root / "head-a-one"
        self.build_follower_snapshot(self.registry, first_snapshot, "leader-a")
        snapshots = {"bafyaone": first_snapshot}

        with patch("clusterctl.follower.ipfs.resolve_name", return_value="bafyaone"), patch(
            "clusterctl.follower.ipfs.fetch_directory", side_effect=self.fake_ipfs_fetch(snapshots)
        ):
            fetch_and_materialize(self.policy, self.output)

        self.policy["trustedLeaders"]["leader-b"]["ipnsName"] = "k51-test-leader-b"
        self.write_event("leader-a", 2, "200::2")
        leader_a_second = self.root / "head-a-two"
        self.build_follower_snapshot(
            self.registry,
            leader_a_second,
            "leader-a",
            previous_cid="bafyaone",
            previous_sequence=1,
        )
        leader_b_registry = self.root / "leader-b-registry"
        self.write_event("leader-b", 2, "200::dead", registry_path=leader_b_registry)
        leader_b_first = self.root / "head-b-one"
        self.build_follower_snapshot(leader_b_registry, leader_b_first, "leader-b")
        snapshots.update({"bafyatwo": leader_a_second, "bafybone": leader_b_first})
        resolved = {
            "k51-test-leader-a": "bafyatwo",
            "k51-test-leader-b": "bafybone",
        }

        with patch("clusterctl.follower.ipfs.resolve_name", side_effect=lambda _policy, name: resolved[name]), patch(
            "clusterctl.follower.ipfs.fetch_directory", side_effect=self.fake_ipfs_fetch(snapshots)
        ):
            fetch_and_materialize(self.policy, self.output)

        self.assertEqual(self.active_generation(), 1)
        conflicts = read_json(self.output / "conflicts.json", {})
        self.assertEqual(conflicts["subjects"]["node-a/yggdrasil"]["generation"], 2)


if __name__ == "__main__":
    unittest.main()
