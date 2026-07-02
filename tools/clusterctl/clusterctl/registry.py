import os
import subprocess
import tempfile
from pathlib import Path

from . import apply as apply_mod
from . import transport
from .canonical import canonical_sha256, event_hash_payload, event_payload, sha256_bytes
from .events import VALID_STATES, iter_json_files, read_json, write_json
from .signing import key_fingerprint, verify_detached_signature, verify_signature

IDENTITY_EVENT_SCHEMA = "cluster.identity.event.v1"
SUPERSEDENCE_SCHEMA = "cluster.identity.supersedence.v1"


ROTATION_SCHEMA = "cluster.identity.rotation.v1"
ROTATION_ACK_SCHEMA = "cluster.identity.rotation-ack.v1"
DELIVERY_RECEIPT_SCHEMA = "cluster.identity.receipt.v1"

def ensure_registry(registry: Path) -> None:
    for name in ["events", "receipts", "bundles", "state", "policy"]:
        (registry / name).mkdir(parents=True, exist_ok=True)


def cluster_id(policy: dict) -> str | None:
    return policy.get("clusterId") or (policy.get("policy") or {}).get("clusterId")


def event_content_hash(event: dict) -> str:
    return canonical_sha256(event_hash_payload(event))


def identity_payload_hash(event: dict) -> str:
    return canonical_sha256(event_payload(event))


def public_identity_fingerprint(service: str, public: dict) -> str | None:
    explicit = public.get("fingerprint")
    if isinstance(explicit, str) and explicit:
        return explicit
    identity_fields = {
        "yggdrasil": "yggdrasilPublicKey",
        "ipns-publisher": "ipnsName",
        "onion-mirror": "onionServicePublicKey",
        "status-ipns": "ipnsName",
        "leader-user-ssh": "publicKey",
        "ssh-host": "sshHostKey",
        "host-age": "ageRecipient",
        "radicle": "radicleNodeId",
        "git-annex": "gitAnnexEndpoint",
    }
    field = identity_fields.get(service)
    value = public.get(field) if field else None
    if service == "ssh-host" and not value:
        value = public.get("publicKey")
    if not isinstance(value, str) or not value:
        return None
    return sha256_bytes(value.encode("utf-8"))


def ensure_public_fingerprint(event: dict) -> None:
    public = event.get("public")
    subject = event.get("subject") or {}
    if not isinstance(public, dict):
        return
    fingerprint = public_identity_fingerprint(subject.get("service"), public)
    if fingerprint:
        public["fingerprint"] = fingerprint


def _finalize_leader_record(registry: Path, record: dict) -> dict:
    leader = record.get("leader")
    if not leader:
        raise ValueError("record requires leader before chain finalization")
    previous = []
    for _path, existing in load_events(registry):
        if existing.get("leader") == leader and isinstance(existing.get("leaderSeq"), int):
            previous.append(existing)
    if previous:
        tip = max(previous, key=lambda item: item["leaderSeq"])
        record["leaderSeq"] = tip["leaderSeq"] + 1
        record["previousLeaderEventHash"] = tip.get("eventHash")
    else:
        record["leaderSeq"] = 1
        record["previousLeaderEventHash"] = None
    record["eventHash"] = event_content_hash(record)
    return record


def finalize_event(registry: Path, event: dict) -> dict:
    event["payloadHash"] = identity_payload_hash(event)
    return _finalize_leader_record(registry, event)


def finalize_supersedence(registry: Path, record: dict) -> dict:
    return _finalize_leader_record(registry, record)


def finalize_rotation(registry: Path, record: dict) -> dict:
    return _finalize_leader_record(registry, record)


def canonical_event_path(registry: Path, event: dict) -> Path:
    return registry / "events" / event["leader"] / f"{event['leaderSeq']:012d}.json"


def init_registry(registry: Path) -> None:
    ensure_registry(registry)
    if not (registry / ".git").exists():
        subprocess.run(["git", "-C", str(registry), "init", "-b", "main"], check=True)
    else:
        subprocess.run(["git", "-C", str(registry), "checkout", "-B", "main"], check=False)
    subprocess.run(
        [
            "git",
            "-C",
            str(registry),
            "config",
            "--local",
            "receive.denyCurrentBranch",
            "updateInstead",
        ],
        check=False,
    )
    transport.ensure_git_identity(registry)


def load_events(registry: Path) -> list[tuple[Path, dict]]:
    events = []
    for path in iter_json_files(registry / "events"):
        events.append((path, read_json(path, {})))
    return events


def identity_events(records: list[tuple[Path, dict]]) -> list[tuple[Path, dict]]:
    return [
        (path, record)
        for path, record in records
        if record.get("schema") == IDENTITY_EVENT_SCHEMA
    ]


def supersedence_records(records: list[tuple[Path, dict]]) -> list[tuple[Path, dict]]:
    return [
        (path, record)
        for path, record in records
        if record.get("schema") == SUPERSEDENCE_SCHEMA
    ]


def rotation_intents(records: list[tuple[Path, dict]]) -> list[tuple[Path, dict]]:
    return [
        (path, record)
        for path, record in records
        if record.get("schema") == ROTATION_SCHEMA
    ]


def delivery_receipts(records: list[tuple[Path, dict]]) -> list[tuple[Path, dict]]:
    return [
        (path, record)
        for path, record in records
        if record.get("schema") == DELIVERY_RECEIPT_SCHEMA
    ]


def rotation_acknowledgements(records: list[tuple[Path, dict]]) -> list[tuple[Path, dict]]:
    return [
        (path, record)
        for path, record in records
        if record.get("schema") == ROTATION_ACK_SCHEMA
    ]


def leader_chain_tip(registry: Path, leader: str) -> dict | None:
    records = [
        record
        for _path, record in load_events(registry)
        if record.get("leader") == leader and isinstance(record.get("leaderSeq"), int)
    ]
    if not records:
        return None
    tip = max(records, key=lambda record: record["leaderSeq"])
    return {
        "leaderSeq": tip["leaderSeq"],
        "eventHash": tip["eventHash"],
    }


def load_receipts(registry: Path) -> list[tuple[Path, dict]]:
    receipts = []
    for path in iter_json_files(registry / "receipts"):
        receipts.append((path, read_json(path, {})))
    return receipts


def load_bundle_manifests(registry: Path) -> list[tuple[Path, dict]]:
    manifests = []
    for path in sorted((registry / "bundles").glob("**/*.manifest.json")):
        if path.is_file():
            manifests.append((path, read_json(path, {})))
    return manifests


def receipt_exists(receipts: list[tuple[Path, dict]], node: str, service: str, generation: int) -> bool:
    for _path, receipt in receipts:
        if (
            receipt.get("node") == node
            and receipt.get("service") == service
            and receipt.get("generation") == generation
            and (receipt.get("activated") is True or receipt.get("status") in {"node-activated", "leader-verified"})
        ):
            return True
    return False


def _valid_public_fields(service: str, public: dict) -> list[str]:
    if not isinstance(public, dict):
        return ["public must be an object"]
    failures: list[str] = []
    if service == "yggdrasil":
        if not public.get("yggdrasilPublicKey"):
            failures.append("yggdrasil public data missing yggdrasilPublicKey")
        if not (public.get("yggdrasilAddress") or public.get("deployHost")):
            failures.append("yggdrasil public data missing yggdrasilAddress or deployHost")
    elif service == "ssh-host":
        if not (public.get("sshHostKey") or public.get("publicKey")):
            failures.append("ssh-host public data missing sshHostKey")
    elif service == "host-age":
        if not public.get("ageRecipient"):
            failures.append("host-age public data missing ageRecipient")
        if public.get("keyType") not in {None, "age-x25519"}:
            failures.append(f"host-age public data has unsupported keyType {public.get('keyType')!r}")
        if not public.get("privateKeyPath"):
            failures.append("host-age public data missing privateKeyPath")
    elif service == "radicle":
        if not public.get("radicleNodeId"):
            failures.append("radicle public data missing radicleNodeId")
    elif service == "git-annex":
        if not public.get("gitAnnexEndpoint"):
            failures.append("git-annex public data missing gitAnnexEndpoint")
    else:
        allowed_unknown = {"sourceTimestamp", "keyGeneratedAt", "fingerprint"}
        if not any(key not in allowed_unknown for key in public):
            failures.append(f"{service} public data has no service-specific fields")
    return failures


def _valid_private_delivery(private_delivery: dict) -> list[str]:
    if not isinstance(private_delivery, dict):
        return ["privateDelivery must be an object or null"]
    failures: list[str] = []
    if private_delivery.get("recipientHost") is not None and not isinstance(private_delivery.get("recipientHost"), str):
        failures.append("privateDelivery.recipientHost must be a string")
    if private_delivery.get("targetPath") is not None and not str(private_delivery.get("targetPath")).startswith("/"):
        failures.append("privateDelivery.targetPath must be absolute")
    if private_delivery.get("requiresReceipt") is not None and not isinstance(private_delivery.get("requiresReceipt"), bool):
        failures.append("privateDelivery.requiresReceipt must be a boolean")
    for field in ["sopsPath", "bundleManifest", "bundlePath", "recipientFingerprint"]:
        if private_delivery.get(field) is not None and not isinstance(private_delivery.get(field), str):
            failures.append(f"privateDelivery.{field} must be a string")
    return failures


def _validate_event_chains(events: list[tuple[Path, dict]]) -> list[str]:
    failures: list[str] = []
    by_leader: dict[str, list[tuple[Path, dict]]] = {}
    for path, event in events:
        leader = event.get("leader")
        if isinstance(leader, str):
            by_leader.setdefault(leader, []).append((path, event))
    for leader, chain in sorted(by_leader.items()):
        chain.sort(key=lambda pair: pair[1].get("leaderSeq", -1))
        previous_hash = None
        expected_sequence = 1
        for path, event in chain:
            sequence = event.get("leaderSeq")
            if sequence != expected_sequence:
                failures.append(f"{path}: {leader} chain expected leaderSeq {expected_sequence}, got {sequence!r}")
                if isinstance(sequence, int):
                    expected_sequence = sequence
            if event.get("previousLeaderEventHash") != previous_hash:
                failures.append(f"{path}: previousLeaderEventHash does not match the {leader} chain tip")
            previous_hash = event.get("eventHash")
            expected_sequence += 1
    return failures


def _safe_registry_path(registry: Path, relative: str) -> Path | None:
    if not isinstance(relative, str) or not relative or relative.startswith("/"):
        return None
    candidate = (registry / relative).resolve()
    try:
        candidate.relative_to(registry.resolve())
    except ValueError:
        return None
    return candidate


def _validate_root(registry: Path, policy: dict) -> list[str]:
    path = registry / "root.json"
    if not path.exists():
        return []
    root = read_json(path, {}) or {}
    failures: list[str] = []
    required = [
        "schema",
        "clusterId",
        "publisher",
        "publisherKeyId",
        "rootSequence",
        "previousRootCid",
        "createdAt",
        "content",
        "signature",
    ]
    for field in required:
        if field not in root:
            failures.append(f"{path}: missing {field}")
    if root.get("schema") != "cluster.identity.root.v1":
        failures.append(f"{path}: invalid schema {root.get('schema')!r}")
    expected_cluster = cluster_id(policy)
    if expected_cluster and root.get("clusterId") != expected_cluster:
        failures.append(f"{path}: clusterId does not match bootstrap policy")
    if not isinstance(root.get("rootSequence"), int) or root.get("rootSequence", 0) < 1:
        failures.append(f"{path}: rootSequence must be a positive integer")
    if "eventChainTip" in root:
        expected_tip = leader_chain_tip(registry, root.get("publisher"))
        if root.get("eventChainTip") != expected_tip:
            failures.append(f"{path}: eventChainTip does not match the publisher chain")
    ok, reason = verify_signature(root, policy.get("trustedLeaders", {}), False)
    if not ok:
        failures.append(f"{path}: {reason}")

    entries: list[dict] = []
    content = root.get("content") or {}
    if not isinstance(content, dict):
        failures.append(f"{path}: content must be an object")
        content = {}
    for category in ["policy", "events", "bundles", "receipts", "state"]:
        if not isinstance(content.get(category), list):
            failures.append(f"{path}: content.{category} must be an array")
    for value in content.values():
        if isinstance(value, dict) and "path" in value:
            entries.append(value)
        elif isinstance(value, list):
            entries.extend(item for item in value if isinstance(item, dict) and "path" in item)
    indexed_paths: set[str] = set()
    for entry in entries:
        relative = entry.get("path")
        if not isinstance(relative, str):
            failures.append(f"{path}: invalid content path {relative!r}")
            continue
        if relative in indexed_paths:
            failures.append(f"{path}: duplicate content path {relative!r}")
            continue
        indexed_paths.add(relative)
        target = _safe_registry_path(registry, relative)
        if target is None:
            failures.append(f"{path}: invalid content path {entry.get('path')!r}")
            continue
        if not target.is_file():
            failures.append(f"{path}: missing content object {entry.get('path')}")
            continue
        actual = sha256_bytes(target.read_bytes())
        if entry.get("sha256") != actual:
            failures.append(f"{path}: digest mismatch for {entry.get('path')}")

    actual_paths = {
        item.relative_to(registry).as_posix()
        for directory in ["policy", "events", "bundles", "receipts", "state"]
        for item in (registry / directory).glob("**/*")
        if item.is_file()
    }
    for unindexed in sorted(actual_paths - indexed_paths):
        failures.append(f"{path}: unindexed snapshot object {unindexed}")
    for missing in sorted(indexed_paths - actual_paths):
        failures.append(f"{path}: indexed object is outside the snapshot source set: {missing}")
    return failures


def _bootstrap_policy_projection(bootstrap: dict) -> tuple[dict, dict, dict]:
    configured_rules = dict(bootstrap.get("policy") or bootstrap)
    configured_rules.pop("signingKeyPath", None)
    thresholds = dict(configured_rules.pop("thresholds", {}))
    leaders = {}
    for name, configured in sorted((bootstrap.get("trustedLeaders") or {}).items()):
        public_key = configured.get("publicSigningKey")
        if not public_key:
            continue
        leaders[name] = {
            "canWrite": configured.get("canWrite", True),
            "keyId": configured.get("keyId") or key_fingerprint(public_key),
            "publicSigningKey": public_key,
            "ipnsName": configured.get("ipnsName"),
            "onionMirror": configured.get("onionMirror"),
            "onionServicePublicKey": configured.get("onionServicePublicKey"),
        }
    return leaders, thresholds, configured_rules


def _validate_leader_policy(registry: Path, bootstrap: dict) -> list[str]:
    path = registry / "policy" / "leader-policy.json"
    if not path.exists():
        return []
    document = read_json(path, {}) or {}
    failures: list[str] = []
    for field in ["schema", "clusterId", "policyGeneration", "leaders", "thresholds", "rules", "signature"]:
        if field not in document:
            failures.append(f"{path}: missing {field}")
    if document.get("schema") != "cluster.identity.policy.v1":
        failures.append(f"{path}: invalid schema {document.get('schema')!r}")
    if cluster_id(bootstrap) and document.get("clusterId") != cluster_id(bootstrap):
        failures.append(f"{path}: clusterId does not match bootstrap policy")
    generation = document.get("policyGeneration")
    if not isinstance(generation, int) or generation < 1:
        failures.append(f"{path}: policyGeneration must be a positive integer")
    envelope = document.get("signature") or {}
    if envelope.get("type") != "openssh-threshold" or envelope.get("namespace") != "cluster-identity":
        failures.append(f"{path}: invalid threshold signature envelope")
        return failures
    valid_leaders: set[str] = set()
    trusted = bootstrap.get("trustedLeaders") or {}
    for signature in envelope.get("signatures") or []:
        leader = signature.get("leader") if isinstance(signature, dict) else None
        trusted_leader = trusted.get(leader) or {}
        public_key = trusted_leader.get("publicSigningKey")
        if not public_key or leader in valid_leaders:
            continue
        detached = {key: value for key, value in signature.items() if key != "leader"}
        ok, _reason = verify_detached_signature(document, public_key, detached, leader)
        if ok:
            valid_leaders.add(leader)
    bootstrap_leaders, bootstrap_thresholds, bootstrap_rules = _bootstrap_policy_projection(bootstrap)
    bootstrap_generation = int(bootstrap_rules.get("policyGeneration", 1))
    if generation is not None and generation < bootstrap_generation:
        failures.append(f"{path}: policyGeneration is older than bootstrap policy")
    is_bootstrap_projection = (
        generation == bootstrap_generation
        and document.get("leaders") == bootstrap_leaders
        and document.get("thresholds") == bootstrap_thresholds
        and document.get("rules") == bootstrap_rules
    )
    required = 1 if is_bootstrap_projection else int(bootstrap_thresholds.get("leaderPolicyUpdate", 2))
    if len(valid_leaders) < required:
        failures.append(f"{path}: policy update has {len(valid_leaders)} valid leader signatures; {required} required")
    return failures


def _validate_supersedences(
    records: list[tuple[Path, dict]],
    policy: dict,
) -> list[str]:
    failures: list[str] = []
    expected_cluster = cluster_id(policy)
    trusted = policy.get("trustedLeaders", {})
    rules = policy.get("policy", policy)
    allow_placeholder = bool(rules.get("allowPlaceholderSignatures", False))
    events_by_hash = {
        event.get("eventHash"): event
        for _path, event in identity_events(records)
        if isinstance(event.get("eventHash"), str)
    }
    for path, record in supersedence_records(records):
        for field in [
            "schema",
            "clusterId",
            "eventId",
            "leader",
            "leaderKeyId",
            "leaderSeq",
            "previousLeaderEventHash",
            "eventHash",
            "subject",
            "superseding",
            "supersedingEvent",
            "superseded",
            "supersededEvent",
            "observedRootCid",
            "reason",
            "createdAt",
            "signature",
        ]:
            if field not in record:
                failures.append(f"{path}: missing {field}")
        if expected_cluster and record.get("clusterId") != expected_cluster:
            failures.append(f"{path}: clusterId does not match bootstrap policy")
        if not isinstance(record.get("leaderSeq"), int) or record.get("leaderSeq", 0) < 1:
            failures.append(f"{path}: leaderSeq must be a positive integer")
        if record.get("eventHash") != event_content_hash(record):
            failures.append(f"{path}: eventHash does not match canonical event preimage")
        subject = record.get("subject") or {}
        if not subject.get("node") or not subject.get("service"):
            failures.append(f"{path}: supersedence subject requires node and service")
        observed_root = record.get("observedRootCid")
        if observed_root is not None and (
            not isinstance(observed_root, str) or not observed_root.isalnum()
        ):
            failures.append(f"{path}: observedRootCid must be null or an alphanumeric CID")
        reason = record.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            failures.append(f"{path}: reason must be a non-empty string")

        referenced: dict[str, dict] = {}
        for name in ["superseding", "superseded"]:
            reference = record.get(name) or {}
            if not isinstance(reference, dict):
                failures.append(f"{path}: {name} must be an object")
                continue
            event_hash = reference.get("eventHash")
            embedded = record.get(f"{name}Event") or {}
            if not isinstance(embedded, dict):
                failures.append(f"{path}: {name}Event must be an object")
                continue
            if embedded.get("schema") != IDENTITY_EVENT_SCHEMA:
                failures.append(f"{path}: {name}Event is not an identity event")
            if embedded.get("eventHash") != event_hash:
                failures.append(f"{path}: {name}Event does not match referenced hash")
            if embedded.get("eventHash") != event_content_hash(embedded):
                failures.append(f"{path}: {name}Event has an invalid eventHash")
            if embedded.get("payloadHash") != identity_payload_hash(embedded):
                failures.append(f"{path}: {name}Event has an invalid payloadHash")
            embedded_ok, embedded_reason = verify_signature(
                embedded, trusted, allow_placeholder
            )
            if not embedded_ok:
                failures.append(f"{path}: {name}Event {embedded_reason}")
            event = events_by_hash.get(event_hash, embedded)
            referenced[name] = event
            for field in ["leader", "generation"]:
                if reference.get(field) != event.get(field):
                    failures.append(f"{path}: {name}.{field} does not match referenced event")
            if event.get("subject") != subject:
                failures.append(f"{path}: {name} event does not match supersedence subject")
        winner = referenced.get("superseding")
        loser = referenced.get("superseded")
        if winner is not None and loser is not None:
            if winner.get("eventHash") == loser.get("eventHash"):
                failures.append(f"{path}: an event cannot supersede itself")
            if winner.get("payloadHash") == loser.get("payloadHash"):
                failures.append(f"{path}: supersedence requires conflicting payloads")
        ok, signature_reason = verify_signature(record, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {signature_reason}")
    return failures


def _rotation_event_fingerprints(event: dict) -> set[str]:
    if event.get("state") == "burned":
        fingerprint = (event.get("burned") or {}).get("fingerprint")
        return {fingerprint} if isinstance(fingerprint, str) and fingerprint else set()
    return _public_fingerprints(event)


def _valid_acknowledgement_policy(path: Path, policy: object) -> list[str]:
    failures: list[str] = []
    if not isinstance(policy, dict):
        return [f"{path}: acknowledgementPolicy must be an object"]
    minimum = policy.get("minimum")
    if not isinstance(minimum, int) or minimum < 0:
        failures.append(f"{path}: acknowledgementPolicy.minimum must be a non-negative integer")
    required_nodes = policy.get("requiredNodes")
    if not isinstance(required_nodes, list) or not all(isinstance(node, str) and node for node in required_nodes):
        failures.append(f"{path}: acknowledgementPolicy.requiredNodes must be a list of node names")
    elif len(set(required_nodes)) != len(required_nodes):
        failures.append(f"{path}: acknowledgementPolicy.requiredNodes must not contain duplicates")
    deadline = policy.get("deadline")
    if not isinstance(deadline, str) or not deadline.endswith("Z") or "T" not in deadline:
        failures.append(f"{path}: acknowledgementPolicy.deadline must be an UTC timestamp string")
    return failures


def _validate_rotation_intents(
    records: list[tuple[Path, dict]],
    policy: dict,
) -> list[str]:
    failures: list[str] = []
    expected_cluster = cluster_id(policy)
    trusted = policy.get("trustedLeaders", {})
    rules = policy.get("policy", policy)
    allow_placeholder = bool(rules.get("allowPlaceholderSignatures", False))
    events_by_hash = {
        event.get("eventHash"): event
        for _path, event in identity_events(records)
        if isinstance(event.get("eventHash"), str)
    }
    for path, record in rotation_intents(records):
        for field in [
            "schema",
            "clusterId",
            "rotationId",
            "eventId",
            "leader",
            "leaderKeyId",
            "policyGeneration",
            "mode",
            "reason",
            "trigger",
            "targets",
            "acknowledgementPolicy",
            "transportOrder",
            "createdAt",
            "leaderSeq",
            "previousLeaderEventHash",
            "eventHash",
            "signature",
        ]:
            if field not in record:
                failures.append(f"{path}: missing {field}")
        if expected_cluster and record.get("clusterId") != expected_cluster:
            failures.append(f"{path}: clusterId does not match bootstrap policy")
        if not isinstance(record.get("leaderSeq"), int) or record.get("leaderSeq", 0) < 1:
            failures.append(f"{path}: leaderSeq must be a positive integer")
        if record.get("eventHash") != event_content_hash(record):
            failures.append(f"{path}: eventHash does not match canonical event preimage")
        if record.get("mode") not in {"graceful", "emergency"}:
            failures.append(f"{path}: mode must be graceful or emergency")
        if not isinstance(record.get("reason"), str) or not record.get("reason", "").strip():
            failures.append(f"{path}: reason must be a non-empty string")
        if not isinstance(record.get("trigger"), dict):
            failures.append(f"{path}: trigger must be an object")
        targets = record.get("targets")
        if not isinstance(targets, list) or not targets:
            failures.append(f"{path}: targets must be a non-empty list")
            targets = []
        for index, target in enumerate(targets):
            if not isinstance(target, dict):
                failures.append(f"{path}: targets[{index}] must be an object")
                continue
            for field in ["node", "service", "generation", "eventHash", "fingerprint", "exposureReason"]:
                if field not in target:
                    failures.append(f"{path}: targets[{index}] missing {field}")
            event = events_by_hash.get(target.get("eventHash"))
            if event is None:
                failures.append(f"{path}: targets[{index}] references an unknown identity event")
                continue
            subject = event.get("subject") or {}
            if target.get("node") != subject.get("node"):
                failures.append(f"{path}: targets[{index}].node does not match referenced event")
            if target.get("service") != subject.get("service"):
                failures.append(f"{path}: targets[{index}].service does not match referenced event")
            if target.get("generation") != event.get("generation"):
                failures.append(f"{path}: targets[{index}].generation does not match referenced event")
            if target.get("fingerprint") not in _rotation_event_fingerprints(event):
                failures.append(f"{path}: targets[{index}].fingerprint does not match referenced event")
            if not isinstance(target.get("exposureReason"), str) or not target.get("exposureReason", "").strip():
                failures.append(f"{path}: targets[{index}].exposureReason must be a non-empty string")
        failures.extend(_valid_acknowledgement_policy(path, record.get("acknowledgementPolicy")))
        acknowledgement_policy = record.get("acknowledgementPolicy") or {}
        waits_for_acknowledgement = (
            acknowledgement_policy.get("minimum") not in {0, None}
            or acknowledgement_policy.get("requiredNodes") not in ([], None)
        )
        if record.get("mode") == "emergency" and waits_for_acknowledgement:
            failures.append(f"{path}: emergency rotations cannot wait for acknowledgements before burn")
        if not isinstance(record.get("transportOrder"), list):
            failures.append(f"{path}: transportOrder must be a list")
        ok, signature_reason = verify_signature(record, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {signature_reason}")
    return failures


def _validate_rotation_acknowledgements(
    receipt_records: list[tuple[Path, dict]],
    event_records: list[tuple[Path, dict]],
    policy: dict,
    trusted_node_keys: dict[str, set[str]],
) -> list[str]:
    failures: list[str] = []
    expected_cluster = cluster_id(policy)
    trusted = policy.get("trustedLeaders", {})
    rules = policy.get("policy", policy)
    allow_placeholder = bool(rules.get("allowPlaceholderSignatures", False))
    rotation_ids = {
        record.get("rotationId")
        for _path, record in rotation_intents(event_records)
        if isinstance(record.get("rotationId"), str)
    }
    replacement_hashes = {
        event.get("eventHash")
        for _path, event in identity_events(event_records)
        if isinstance(event.get("eventHash"), str)
    }
    for path, acknowledgement in rotation_acknowledgements(receipt_records):
        for field in [
            "schema",
            "clusterId",
            "rotationId",
            "node",
            "replacementEventHashes",
            "acceptedRootCid",
            "acceptedAt",
            "signedByNode",
            "signature",
        ]:
            if field not in acknowledgement:
                failures.append(f"{path}: missing {field}")
        if expected_cluster and acknowledgement.get("clusterId") != expected_cluster:
            failures.append(f"{path}: clusterId does not match bootstrap policy")
        if acknowledgement.get("rotationId") not in rotation_ids:
            failures.append(f"{path}: rotationId does not reference a known rotation intent")
        hashes = acknowledgement.get("replacementEventHashes")
        if not isinstance(hashes, list) or not hashes:
            failures.append(f"{path}: replacementEventHashes must be a non-empty list")
            hashes = []
        for event_hash in hashes:
            if event_hash not in replacement_hashes:
                failures.append(f"{path}: replacementEventHashes contains an unknown identity event")
        accepted_root = acknowledgement.get("acceptedRootCid")
        if not isinstance(accepted_root, str) or not accepted_root:
            failures.append(f"{path}: acceptedRootCid must be a non-empty string")
        if not isinstance(acknowledgement.get("acceptedAt"), str) or "T" not in acknowledgement.get("acceptedAt", ""):
            failures.append(f"{path}: acceptedAt must be a timestamp string")
        ok, reason = verify_signature(acknowledgement, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {reason}")
        signed_by_node = acknowledgement.get("signedByNode") or {}
        receipt_key = signed_by_node.get("publicKey") if isinstance(signed_by_node, dict) else signed_by_node
        if receipt_key not in trusted_node_keys.get(acknowledgement.get("node"), set()):
            failures.append(f"{path}: acknowledgement is not signed by a registered ssh-host key for {acknowledgement.get('node')}")
    return failures


def validate_registry(registry: Path, policy: dict | None = None) -> list[str]:
    policy = policy or {}
    trusted = policy.get("trustedLeaders", {})
    rules = policy.get("policy", policy)
    allow_placeholder = bool(rules.get("allowPlaceholderSignatures", False))
    failures: list[str] = []
    receipt_records = load_receipts(registry)
    receipts = delivery_receipts(receipt_records)
    records = load_events(registry)
    events = identity_events(records)
    supported_event_schemas = {
        IDENTITY_EVENT_SCHEMA,
        SUPERSEDENCE_SCHEMA,
        ROTATION_SCHEMA,
    }
    for path, record in records:
        if record.get("schema") not in supported_event_schemas:
            failures.append(f"{path}: unsupported registry record schema {record.get('schema')!r}")
    for path, record in receipt_records:
        if record.get("schema") not in {DELIVERY_RECEIPT_SCHEMA, ROTATION_ACK_SCHEMA}:
            failures.append(f"{path}: unsupported receipt record schema {record.get('schema')!r}")
    burned: set[str] = set()
    expected_cluster = cluster_id(policy)
    trusted_node_keys: dict[str, set[str]] = {}
    for _event_path, event in events:
        subject = event.get("subject") or {}
        if subject.get("service") != "ssh-host" or event.get("state") == "burned":
            continue
        public = event.get("public") or {}
        public_key = public.get("sshHostKey") or public.get("publicKey")
        if public_key:
            trusted_node_keys.setdefault(subject.get("node"), set()).add(public_key)

    for path, event in events:
        subject = event.get("subject") or {}
        for field in [
            "schema",
            "clusterId",
            "eventId",
            "leader",
            "leaderKeyId",
            "leaderSeq",
            "previousLeaderEventHash",
            "eventHash",
            "payloadHash",
            "subject",
            "generation",
            "state",
            "createdAt",
            "signature",
        ]:
            if field not in event:
                failures.append(f"{path}: missing {field}")
        if event.get("schema") != "cluster.identity.event.v1":
            failures.append(f"{path}: invalid schema {event.get('schema')!r}")
        if expected_cluster and event.get("clusterId") != expected_cluster:
            failures.append(f"{path}: clusterId does not match bootstrap policy")
        if not subject.get("node"):
            failures.append(f"{path}: missing subject.node")
        if not subject.get("service"):
            failures.append(f"{path}: missing subject.service")
        if not isinstance(event.get("generation"), int):
            failures.append(f"{path}: generation must be an integer")
        if event.get("state") not in VALID_STATES:
            failures.append(f"{path}: invalid state {event.get('state')!r}")
        if not isinstance(event.get("leaderSeq"), int) or event.get("leaderSeq", 0) < 1:
            failures.append(f"{path}: leaderSeq must be a positive integer")
        if event.get("eventHash") != event_content_hash(event):
            failures.append(f"{path}: eventHash does not match canonical event preimage")
        if event.get("payloadHash") != identity_payload_hash(event):
            failures.append(f"{path}: payloadHash does not match canonical identity payload")
        if event.get("public") is not None:
            for failure in _valid_public_fields(subject.get("service"), event.get("public") or {}):
                failures.append(f"{path}: {failure}")
        private_delivery = event.get("privateDelivery")
        if private_delivery is not None:
            for failure in _valid_private_delivery(private_delivery):
                failures.append(f"{path}: {failure}")
        ok, reason = verify_signature(event, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {reason}")
        if event.get("state") == "burned":
            fingerprint = (event.get("burned") or {}).get("fingerprint")
            if not fingerprint:
                failures.append(f"{path}: burned event missing burned.fingerprint")
            else:
                burned.add(fingerprint)
        private_delivery = event.get("privateDelivery") or {}
        requires_receipt = bool(private_delivery.get("requiresReceipt"))
        if (
            rules.get("requireReceiptBeforePromote", False)
            and requires_receipt
            and event.get("state") == "active"
            and isinstance(event.get("generation"), int)
            and not receipt_exists(receipts, subject.get("node"), subject.get("service"), event["generation"])
        ):
            failures.append(f"{path}: active private-delivery event is missing activation receipt")

    failures.extend(_validate_supersedences(records, policy))
    failures.extend(_validate_rotation_intents(records, policy))
    failures.extend(_validate_event_chains(records))

    for path, receipt in receipts:
        for field in ["schema", "clusterId", "node", "service", "generation", "status", "createdAt", "signedByNode", "signature"]:
            if field not in receipt:
                failures.append(f"{path}: missing {field}")
        if receipt.get("schema") != DELIVERY_RECEIPT_SCHEMA:
            failures.append(f"{path}: invalid schema {receipt.get('schema')!r}")
        if expected_cluster and receipt.get("clusterId") != expected_cluster:
            failures.append(f"{path}: clusterId does not match bootstrap policy")
        if not isinstance(receipt.get("generation"), int):
            failures.append(f"{path}: generation must be an integer")
        ok, reason = verify_signature(receipt, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {reason}")
        signed_by_node = receipt.get("signedByNode") or {}
        receipt_key = signed_by_node.get("publicKey") if isinstance(signed_by_node, dict) else signed_by_node
        if receipt_key not in trusted_node_keys.get(receipt.get("node"), set()):
            failures.append(f"{path}: receipt is not signed by a registered ssh-host key for {receipt.get('node')}")

    failures.extend(_validate_rotation_acknowledgements(receipt_records, records, policy, trusted_node_keys))

    for path, manifest in load_bundle_manifests(registry):
        for field in ["schema", "clusterId", "subject", "generation", "targetPath", "encryption", "bundle", "leader", "leaderKeyId", "signature"]:
            if field not in manifest:
                failures.append(f"{path}: missing {field}")
        if manifest.get("schema") != "cluster.identity.bundle.v1":
            failures.append(f"{path}: invalid schema {manifest.get('schema')!r}")
        if expected_cluster and manifest.get("clusterId") != expected_cluster:
            failures.append(f"{path}: clusterId does not match bootstrap policy")
        subject = manifest.get("subject") or {}
        if not subject.get("node"):
            failures.append(f"{path}: missing subject.node")
        if not subject.get("service"):
            failures.append(f"{path}: missing subject.service")
        if not isinstance(manifest.get("generation"), int):
            failures.append(f"{path}: generation must be an integer")
        encryption = manifest.get("encryption") or {}
        if encryption.get("method") != "age-x25519":
            failures.append(f"{path}: unsupported encryption method {encryption.get('method')!r}")
        if not encryption.get("recipientPublicKey"):
            failures.append(f"{path}: missing encryption.recipientPublicKey")
        bundle = manifest.get("bundle") or {}
        if not bundle.get("path"):
            failures.append(f"{path}: missing bundle.path")
        else:
            ciphertext = _safe_registry_path(registry, bundle["path"])
            if ciphertext is None or not ciphertext.is_file():
                failures.append(f"{path}: bundle ciphertext is missing or outside the registry")
            elif bundle.get("ciphertextSha256") != sha256_bytes(ciphertext.read_bytes()):
                failures.append(f"{path}: bundle ciphertextSha256 does not match ciphertext")
        ok, reason = verify_signature(manifest, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {reason}")

    failures.extend(_validate_root(registry, policy))
    failures.extend(_validate_leader_policy(registry, policy))
    return failures


def _empty_generated(generated_from: list[str]) -> dict:
    return {
        "schema": "cluster.identity.state.v1",
        "generatedFrom": generated_from,
        "nodes": {},
    }


def _put(state: dict, node: str, service: str, event: dict) -> None:
    state["nodes"].setdefault(node, {})[service] = {
        "generation": event["generation"],
        "state": event["state"],
        "leader": event.get("leader"),
        "eventId": event.get("eventId"),
        "eventHash": event.get("eventHash"),
        "public": event.get("public", {}),
        "privateDelivery": event.get("privateDelivery"),
        "localUsable": event.get("localUsable", True),
        "createdAt": event.get("createdAt"),
        "payloadHash": event.get("payloadHash"),
    }


def _event_order(event: dict) -> tuple[str, int]:
    public = event.get("public") or {}
    key_generated_at = (
        public.get("keyGeneratedAt")
        or public.get("sourceTimestamp")
        or event.get("keyGeneratedAt")
        or event.get("sourceTimestamp")
        or ""
    )
    generation = event.get("generation")
    return (key_generated_at, generation if isinstance(generation, int) else -1)


STATE_NAMES = ["active", "staged", "deprecated", "burned"]

STATE_PRECEDENCE = {
    "planned": 0,
    "staged": 1,
    "private-delivered": 2,
    "node-received": 3,
    "node-activated": 4,
    "leader-verified": 5,
    "active": 6,
    "deprecated": 7,
    "removed": 8,
}


def _copy_state(state: dict | None, generated: list[str]) -> dict:
    if not isinstance(state, dict):
        return _empty_generated(generated)
    copied = {
        "schema": "cluster.identity.state.v1",
        "clusterId": state.get("clusterId"),
        "generatedFrom": generated,
        "nodes": {},
    }
    for node, services in (state.get("nodes") or {}).items():
        copied["nodes"][node] = {service: dict(value) for service, value in services.items()}
    return copied


def _remove_subject(states: list[dict], node: str, service: str) -> None:
    for state in states:
        services = (state.get("nodes") or {}).get(node)
        if not services:
            continue
        services.pop(service, None)
        if not services:
            state["nodes"].pop(node, None)


def _public_fingerprints(event: dict) -> set[str]:
    public = event.get("public") or {}
    fingerprints = {
        value
        for key, value in public.items()
        if "fingerprint" in key.lower() and isinstance(value, str)
    }
    subject = event.get("subject") or {}
    derived = public_identity_fingerprint(subject.get("service"), public)
    if derived:
        fingerprints.add(derived)
    return fingerprints


def local_state_path(policy: dict) -> Path:
    configured = policy.get("localStatePath") or (policy.get("registry") or {}).get("localStatePath")
    return Path(configured or "/var/lib/cluster-identity/local-state")


def load_checkpoint(policy: dict) -> dict:
    checkpoint = read_json(local_state_path(policy) / "checkpoint.json", {}) or {}
    return checkpoint if isinstance(checkpoint, dict) else {}


def update_checkpoint(policy: dict, updates: dict) -> dict:
    checkpoint = load_checkpoint(policy)
    checkpoint.update(updates)
    _atomic_write_json(local_state_path(policy) / "checkpoint.json", checkpoint)
    return checkpoint


def _read_last_good(local_state: Path, name: str) -> dict | None:
    return read_json(local_state / "last-good" / f"{name}.json", None)


def _atomic_write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        write_json(temporary, value)
        try:
            os.chown(temporary, -1, path.parent.stat().st_gid)
        except PermissionError:
            pass
        temporary.chmod(0o660)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        temporary = Path(handle.name)
        handle.write(value)
    try:
        try:
            os.chown(temporary, -1, path.parent.stat().st_gid)
        except PermissionError:
            pass
        temporary.chmod(0o664)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _supersedence_edges(
    records: list[tuple[Path, dict]],
) -> dict[tuple[str, str], list[tuple[str, str, str]]]:
    edges: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for _path, record in supersedence_records(records):
        subject = record["subject"]
        key = (subject["node"], subject["service"])
        edges.setdefault(key, []).append(
            (
                record["superseding"]["eventHash"],
                record["superseded"]["eventHash"],
                record["eventId"],
            )
        )
    return edges


def _cyclic_resolution_nodes(edges: list[tuple[str, str, str]]) -> set[str]:
    graph: dict[str, set[str]] = {}
    for winner, loser, _resolution_id in edges:
        graph.setdefault(winner, set()).add(loser)
    visiting: set[str] = set()
    visited: set[str] = set()
    cyclic: set[str] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in visiting:
            cyclic.update(path[path.index(node) :])
            return
        if node in visited:
            return
        visiting.add(node)
        path.append(node)
        for child in graph.get(node, set()):
            visit(child, path)
        path.pop()
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node, [])
    return cyclic


def _resolution_reaches(
    edges: list[tuple[str, str, str]],
    winner_hash: str,
    loser_hash: str,
) -> bool:
    graph: dict[str, set[str]] = {}
    for winner, loser, _resolution_id in edges:
        graph.setdefault(winner, set()).add(loser)
    pending = [winner_hash]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current == loser_hash:
            return True
        if current in seen:
            continue
        seen.add(current)
        pending.extend(graph.get(current, set()) - seen)
    return False


def _replacement_candidates(target: dict, events: list[dict]) -> list[dict]:
    candidates: list[dict] = []
    for event in events:
        subject = event.get("subject") or {}
        if subject.get("node") != target.get("node") or subject.get("service") != target.get("service"):
            continue
        generation = event.get("generation")
        if not isinstance(generation, int) or generation <= target.get("generation", -1):
            continue
        if event.get("state") == "burned":
            continue
        candidates.append(event)
    return candidates


def _old_generation_deprecated(target: dict, events: list[dict]) -> bool:
    for event in events:
        subject = event.get("subject") or {}
        if subject.get("node") != target.get("node") or subject.get("service") != target.get("service"):
            continue
        if event.get("generation") != target.get("generation") or event.get("state") != "deprecated":
            continue
        if target.get("fingerprint") in _rotation_event_fingerprints(event):
            return True
    return False


def _acknowledgement_summary(intent: dict, replacement_hashes: set[str], acknowledgements: list[dict]) -> dict:
    policy = intent.get("acknowledgementPolicy") or {}
    required = set(policy.get("requiredNodes") or [])
    acknowledged = {
        acknowledgement.get("node")
        for acknowledgement in acknowledgements
        if acknowledgement.get("rotationId") == intent.get("rotationId")
        and replacement_hashes.intersection(acknowledgement.get("replacementEventHashes") or [])
    }
    acknowledged.discard(None)
    minimum = policy.get("minimum") if isinstance(policy.get("minimum"), int) else 0
    missing_required = sorted(required - acknowledged)
    return {
        "minimum": minimum,
        "requiredNodes": sorted(required),
        "deadline": policy.get("deadline"),
        "acknowledgedNodes": sorted(acknowledged),
        "missingRequiredNodes": missing_required,
        "satisfied": len(acknowledged) >= minimum and not missing_required,
    }


def _derive_rotations(
    records: list[tuple[Path, dict]],
    receipt_records: list[tuple[Path, dict]],
    generated: list[str],
    expected_cluster: str | None,
) -> dict:
    events = [event for _path, event in identity_events(records)]
    acknowledgements = [ack for _path, ack in rotation_acknowledgements(receipt_records)]
    burned_fingerprints = {
        fingerprint
        for event in events
        for fingerprint in _rotation_event_fingerprints(event)
        if event.get("state") == "burned"
    }
    rotations: dict[str, dict] = {}
    precedence = {
        "replacement-pending": 0,
        "awaiting-acknowledgements": 1,
        "ready-to-retire": 2,
        "deprecated": 3,
        "complete": 4,
        "emergency-incomplete": 5,
    }
    for _path, intent in rotation_intents(records):
        target_views: list[dict] = []
        target_statuses: list[str] = []
        for target in intent.get("targets") or []:
            replacements = _replacement_candidates(target, events)
            replacement_hashes = {event["eventHash"] for event in replacements if isinstance(event.get("eventHash"), str)}
            active_replacements = [event for event in replacements if event.get("state") == "active"]
            staged_replacements = [event for event in replacements if event.get("state") == "staged"]
            acknowledgement = _acknowledgement_summary(intent, replacement_hashes, acknowledgements)
            old_burned = target.get("fingerprint") in burned_fingerprints
            old_deprecated = _old_generation_deprecated(target, events)
            if old_burned and (active_replacements or intent.get("mode") != "emergency"):
                status = "complete"
            elif old_burned:
                status = "emergency-incomplete"
            elif old_deprecated:
                status = "deprecated"
            elif active_replacements and acknowledgement["satisfied"]:
                status = "ready-to-retire"
            elif active_replacements:
                status = "awaiting-acknowledgements"
            else:
                status = "replacement-pending"
            target_statuses.append(status)
            target_views.append(
                {
                    "node": target.get("node"),
                    "service": target.get("service"),
                    "generation": target.get("generation"),
                    "eventHash": target.get("eventHash"),
                    "fingerprint": target.get("fingerprint"),
                    "exposureReason": target.get("exposureReason"),
                    "status": status,
                    "replacementEventHashes": sorted(replacement_hashes),
                    "stagedReplacementEventHashes": sorted(
                        event["eventHash"] for event in staged_replacements if isinstance(event.get("eventHash"), str)
                    ),
                    "activeReplacementEventHashes": sorted(
                        event["eventHash"] for event in active_replacements if isinstance(event.get("eventHash"), str)
                    ),
                    "acknowledgement": acknowledgement,
                    "oldDeprecated": old_deprecated,
                    "oldBurned": old_burned,
                }
            )
        if not target_statuses:
            status = "blocked"
        elif all(item == "complete" for item in target_statuses):
            status = "complete"
        elif any(item == "emergency-incomplete" for item in target_statuses):
            status = "emergency-incomplete"
        else:
            status = min(target_statuses, key=lambda item: precedence.get(item, -1))
        rotations[intent["rotationId"]] = {
            "rotationId": intent.get("rotationId"),
            "eventId": intent.get("eventId"),
            "eventHash": intent.get("eventHash"),
            "leader": intent.get("leader"),
            "mode": intent.get("mode"),
            "reason": intent.get("reason"),
            "trigger": intent.get("trigger"),
            "status": status,
            "createdAt": intent.get("createdAt"),
            "acknowledgementPolicy": intent.get("acknowledgementPolicy"),
            "targets": target_views,
        }
    return {
        "schema": "cluster.identity.rotations.v1",
        "clusterId": expected_cluster,
        "generatedFrom": generated,
        "rotations": rotations,
    }


def reconcile(registry: Path, out: Path | None = None, policy: dict | None = None) -> None:
    ensure_registry(registry)
    policy = policy or {}
    failures = validate_registry(registry, policy)
    if failures:
        raise ValueError("registry verification failed:\n" + "\n".join(f"- {failure}" for failure in failures))
    rules = policy.get("policy", policy)
    receipt_records = load_receipts(registry)
    receipts = delivery_receipts(receipt_records)
    records = load_events(registry)
    event_pairs = identity_events(records)
    resolution_edges = _supersedence_edges(records)
    local_host = policy.get("hostName")
    host_age_key = policy.get("sopsAgeKeyFile") or policy.get("hostAgeKeyFile")
    generated = [record.get("eventId") for _path, record in records if record.get("eventId")]
    local_state = local_state_path(policy)
    checkpoint = load_checkpoint(policy)
    policy_generation = int(rules.get("policyGeneration", 1))
    checkpoint_policy_generation = int(checkpoint.get("policyGeneration", 0))
    if policy_generation < checkpoint_policy_generation:
        raise ValueError(
            "registry policy rollback rejected: "
            f"generation {policy_generation} is below checkpoint {checkpoint_policy_generation}"
        )
    accepted_subjects = dict(checkpoint.get("subjects") or {})
    burned_fingerprints = set(checkpoint.get("burnedFingerprints") or [])
    active = _copy_state(_read_last_good(local_state, "active"), generated)
    staged = _copy_state(_read_last_good(local_state, "staged"), generated)
    deprecated = _copy_state(_read_last_good(local_state, "deprecated"), generated)
    burned = _copy_state(_read_last_good(local_state, "burned"), generated)
    states = [active, staged, deprecated, burned]
    conflicts: dict[str, dict] = {}
    events_by_subject: dict[tuple[str, str], list[dict]] = {}
    burn_events: dict[tuple[str, str], list[dict]] = {}

    for _path, event in event_pairs:
        subject = event["subject"]
        key = (subject["node"], subject["service"])
        if event["state"] == "burned":
            burn_events.setdefault(key, []).append(event)
            burned_fingerprints.add(event["burned"]["fingerprint"])
        else:
            events_by_subject.setdefault(key, []).append(event)

    for (node, service), subject_burns in burn_events.items():
        latest_burn = max(subject_burns, key=lambda item: (item["generation"], item["leaderSeq"]))
        _remove_subject([active, staged, deprecated], node, service)
        _put(burned, node, service, latest_burn)
        accepted_subjects[f"{node}/{service}"] = {
            "generation": latest_burn["generation"],
            "payloadHash": latest_burn["payloadHash"],
            "eventHash": latest_burn["eventHash"],
            "state": "burned",
        }

    thresholds = rules.get("thresholds") or {}
    for (node, service), subject_events in sorted(events_by_subject.items()):
        usable = [event for event in subject_events if not (_public_fingerprints(event) & burned_fingerprints)]
        if not usable:
            continue
        subject_key = f"{node}/{service}"
        usable_hashes = {event["eventHash"] for event in usable}
        edges = [
            edge
            for edge in resolution_edges.get((node, service), [])
            if edge[0] in usable_hashes and edge[1] in usable_hashes
        ]
        cyclic = _cyclic_resolution_nodes(edges)
        if cyclic:
            conflicts[subject_key] = {
                "action": "kept-last-good",
                "reason": "cyclic-supersedence",
                "eventHashes": sorted(cyclic),
            }
            continue
        superseded_hashes = {loser for _winner, loser, _resolution_id in edges}
        eligible = [
            event for event in usable if event["eventHash"] not in superseded_hashes
        ]
        if not eligible:
            conflicts[subject_key] = {
                "action": "kept-last-good",
                "reason": "supersedence-left-no-candidate",
            }
            continue
        highest_generation = max(event["generation"] for event in eligible)
        generation_events = [
            event for event in eligible if event["generation"] == highest_generation
        ]
        payloads: dict[str, list[dict]] = {}
        for event in generation_events:
            payloads.setdefault(event["payloadHash"], []).append(event)
        accepted = accepted_subjects.get(subject_key) or {}
        accepted_generation = accepted.get("generation", -1)
        if len(payloads) != 1:
            conflicts[subject_key] = {
                "generation": highest_generation,
                "payloadHashes": sorted(payloads),
                "candidates": [
                    {
                        "eventHash": event["eventHash"],
                        "leader": event["leader"],
                        "generation": event["generation"],
                        "payloadHash": event["payloadHash"],
                    }
                    for event in generation_events
                ],
                "action": "kept-last-good",
            }
            continue
        payload_hash, matching_events = next(iter(payloads.items()))
        accepted_event_hash = accepted.get("eventHash")
        accepted_event_hashes = (
            {accepted_event_hash}
            if isinstance(accepted_event_hash, str)
            else {
                event["eventHash"]
                for event in subject_events
                if event.get("generation") == accepted_generation
                and event.get("payloadHash") == accepted.get("payloadHash")
            }
        )
        accepted_is_burned = accepted.get("state") == "burned"
        resolution_authorized = any(
            _resolution_reaches(edges, event["eventHash"], prior_hash)
            for event in matching_events
            for prior_hash in accepted_event_hashes
        )
        rollback = not accepted_is_burned and (
            highest_generation < accepted_generation
            or (
                highest_generation == accepted_generation
                and accepted.get("payloadHash") not in {None, payload_hash}
            )
        )
        if rollback and not resolution_authorized:
            conflicts[subject_key] = {
                "generation": highest_generation,
                "payloadHashes": [payload_hash],
                "action": "rejected-rollback",
            }
            continue

        required_signers = 1
        if service == "host-age" and highest_generation > accepted_generation:
            required_signers = int(thresholds.get("hostAgeRotation", 2))
        leaders = {event["leader"] for event in matching_events}
        selected = max(
            matching_events,
            key=lambda item: (
                any(
                    _resolution_reaches(edges, item["eventHash"], prior_hash)
                    for prior_hash in accepted_event_hashes
                ),
                STATE_PRECEDENCE.get(item["state"], -1),
                item["leaderSeq"],
            ),
        )
        selected = dict(selected)
        state = selected["state"]
        if len(leaders) < required_signers:
            state = "staged"
            selected["localUsable"] = False
        private_delivery = selected.get("privateDelivery") or {}
        if state == "active" and rules.get("requireReceiptBeforePromote", False) and private_delivery.get("requiresReceipt"):
            if not receipt_exists(receipts, node, service, highest_generation):
                state = "staged"
                selected["localUsable"] = False
        if state == "active" and local_host == node and private_delivery.get("bundleManifest"):
            manifest = registry / private_delivery["bundleManifest"]
            if not _manifest_decryptable(registry, manifest, host_age_key):
                state = "staged"
                selected["localUsable"] = False

        selected["state"] = state
        _remove_subject([active, staged, deprecated], node, service)
        if state == "active":
            _put(active, node, service, selected)
        elif state == "deprecated":
            _put(deprecated, node, service, selected)
        elif state != "removed":
            _put(staged, node, service, selected)
        if len(leaders) >= required_signers and (
            highest_generation >= accepted_generation or resolution_authorized
        ):
            accepted_subjects[subject_key] = {
                "generation": highest_generation,
                "payloadHash": payload_hash,
                "eventHash": selected["eventHash"],
                "state": state,
            }

    expected_cluster = cluster_id(policy)
    for state in states:
        state["clusterId"] = expected_cluster
    conflict_state = {
        "schema": "cluster.identity.conflicts.v1",
        "clusterId": expected_cluster,
        "generatedFrom": generated,
        "subjects": conflicts,
    }
    rotations = _derive_rotations(records, receipt_records, generated, expected_cluster)

    if out is None:
        _write_registry_state(registry, active, staged, deprecated, burned, conflict_state, rotations)
    else:
        _write_materialized_state(out, active, staged, deprecated, burned, conflict_state, rotations)

    for name, state in zip(STATE_NAMES, states, strict=True):
        _atomic_write_json(local_state / "last-good" / f"{name}.json", state)
    _atomic_write_json(local_state / "last-good" / "rotations.json", rotations)
    next_checkpoint = dict(checkpoint)
    next_checkpoint.update(
        {
            "schema": "cluster.identity.checkpoint.v1",
            "clusterId": expected_cluster,
            "subjects": accepted_subjects,
            "burnedFingerprints": sorted(burned_fingerprints),
            "policyGeneration": policy_generation,
            "acceptedCids": checkpoint.get("acceptedCids") or [],
        }
    )
    _atomic_write_json(local_state / "checkpoint.json", next_checkpoint)


def _manifest_decryptable(registry: Path, manifest: Path, host_age_key: str | None) -> bool:
    if not host_age_key:
        return False
    manifest_data = read_json(manifest, {}) or {}
    bundle = manifest_data.get("bundle") or {}
    bundle_path = bundle.get("path")
    if not bundle_path:
        return False
    encrypted = registry / bundle_path
    if not encrypted.exists():
        encrypted = manifest.parent / Path(bundle_path).name
    if not encrypted.exists():
        return False
    completed = subprocess.run(
        ["age", "-d", "-i", host_age_key, str(encrypted)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _service_views(active: dict) -> tuple[list[str], dict[str, dict], dict[str, dict], dict[str, dict]]:
    known_hosts: list[str] = []
    yggdrasil: dict[str, dict] = {}
    radicle: dict[str, dict] = {}
    annex: dict[str, dict] = {}
    for node, services in active.get("nodes", {}).items():
        ssh = services.get("ssh-host", {}).get("public", {})
        ssh_key = ssh.get("sshHostKey") or ssh.get("publicKey")
        if ssh_key:
            known_hosts.append(f"{node} {ssh_key}")
        ygg = services.get("yggdrasil", {}).get("public", {})
        if ygg:
            yggdrasil[node] = ygg
        rad = services.get("radicle", {}).get("public", {})
        if rad:
            radicle[node] = rad
        git_annex = services.get("git-annex", {}).get("public", {})
        if git_annex:
            annex[node] = git_annex
    return known_hosts, yggdrasil, radicle, annex


def _safe_ssh_token(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not any(character.isspace() or ord(character) < 32 for character in value)
        and not any(character in value for character in ["#", "'", '"', "\\"])
    )


def _ssh_config(yggdrasil: dict[str, dict]) -> str:
    blocks: list[str] = []
    for node, public in sorted(yggdrasil.items()):
        target = public.get("deployHost") or public.get("yggdrasilAddress")
        ygg_alias = f"{node}-ygg"
        if not all(_safe_ssh_token(value) for value in [node, ygg_alias, target]):
            continue
        blocks.extend(
            [
                f"Host {node} {ygg_alias}",
                f"  HostName {target}",
                f"  HostKeyAlias {node}",
                "",
            ]
        )
    return "\n".join(blocks)


def _write_registry_state(
    registry: Path,
    active: dict,
    staged: dict,
    deprecated: dict,
    burned: dict,
    conflicts: dict,
    rotations: dict,
) -> None:
    state = registry / "state"
    state.mkdir(parents=True, exist_ok=True)
    write_json(state / "active.json", active)
    write_json(state / "staged.json", staged)
    write_json(state / "deprecated.json", deprecated)
    write_json(state / "burned.json", burned)
    write_json(state / "conflicts.json", conflicts)
    write_json(state / "rotations.json", rotations)
    known_hosts, yggdrasil, radicle, annex = _service_views(active)
    (state / "known_hosts").write_text("\n".join(known_hosts) + ("\n" if known_hosts else ""), encoding="utf-8")
    (state / "ssh_config").write_text(_ssh_config(yggdrasil), encoding="utf-8")
    write_json(state / "yggdrasil-peers.json", yggdrasil)
    write_json(state / "radicle-nodes.json", radicle)
    write_json(state / "git-annex-remotes.json", annex)


def _write_materialized_state(
    out: Path,
    active: dict,
    staged: dict,
    deprecated: dict,
    burned: dict,
    conflicts: dict,
    rotations: dict,
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "active.json", active)
    write_json(out / "staged.json", staged)
    write_json(out / "deprecated.json", deprecated)
    write_json(out / "burned.json", burned)
    write_json(out / "conflicts.json", conflicts)
    write_json(out / "rotations.json", rotations)
    known_hosts, yggdrasil, radicle, annex = _service_views(active)
    (out / "ssh_known_hosts").write_text("\n".join(known_hosts) + ("\n" if known_hosts else ""), encoding="utf-8")
    _atomic_write_text(out / "ssh_config", _ssh_config(yggdrasil))
    for subdir in ["yggdrasil", "radicle", "git-annex"]:
        (out / subdir).mkdir(parents=True, exist_ok=True)
    write_json(out / "yggdrasil" / "peers.json", yggdrasil)
    write_json(out / "radicle" / "nodes.json", radicle)
    write_json(out / "git-annex" / "remotes.json", annex)


def sync(registry: Path, out: Path, policy: dict | None = None) -> None:
    transport.git_fetch_all(registry, policy)
    reconcile(registry, out, policy)
    apply_mod.apply_materialized(registry, out, policy)
