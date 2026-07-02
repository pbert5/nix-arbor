import os
import shutil
import tempfile
from pathlib import Path

from . import announcements, ipfs, onion
from .canonical import sha256_bytes
from .events import now_utc, read_json, write_json
from .registry import cluster_id, leader_chain_tip, reconcile, validate_registry
from .signing import key_fingerprint, public_key_from_private, sign_record


CONTENT_GLOBS = {
    "events": ("events", "**/*.json"),
    "bundles": ("bundles", "**/*"),
    "receipts": ("receipts", "**/*.json"),
    "state": ("state", "*.json"),
}


def _public_rules(policy: dict) -> tuple[dict, dict]:
    configured = dict(policy.get("policy") or policy)
    configured.pop("signingKeyPath", None)
    thresholds = dict(configured.pop("thresholds", {}))
    return configured, thresholds


def _public_leaders(policy: dict) -> dict:
    leaders = {}
    for name, configured in sorted((policy.get("trustedLeaders") or {}).items()):
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
    return leaders


def leader_policy_document(
    policy: dict,
    publisher: str,
    signing_key: Path,
) -> dict:
    rules, thresholds = _public_rules(policy)
    document = {
        "schema": "cluster.identity.policy.v1",
        "clusterId": cluster_id(policy),
        "policyGeneration": int(rules.get("policyGeneration", 1)),
        "leaders": _public_leaders(policy),
        "thresholds": thresholds,
        "rules": rules,
    }
    signature = sign_record(document, signing_key)
    document["signature"] = {
        "type": "openssh-threshold",
        "namespace": "cluster-identity",
        "signatures": [
            {
                "leader": publisher,
                **signature,
            }
        ],
    }
    return document


def _copy_content(registry: Path, snapshot: Path) -> None:
    for _category, (directory_name, pattern) in CONTENT_GLOBS.items():
        source_root = registry / directory_name
        if not source_root.exists():
            continue
        for source in sorted(source_root.glob(pattern)):
            if not source.is_file():
                continue
            if directory_name == "bundles" and source.suffix not in {".age", ".json"}:
                continue
            relative = source.relative_to(registry)
            destination = snapshot / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)


def _content_index(snapshot: Path) -> dict[str, list[dict]]:
    content: dict[str, list[dict]] = {"policy": []}
    for category in CONTENT_GLOBS:
        content[category] = []
    for path in sorted(snapshot.glob("**/*")):
        if not path.is_file() or path.name == "root.json":
            continue
        relative = path.relative_to(snapshot).as_posix()
        category = relative.split("/", 1)[0]
        content.setdefault(category, []).append(
            {
                "path": relative,
                "sha256": sha256_bytes(path.read_bytes()),
            }
        )
    return content


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        write_json(temporary, value)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publisher_state_path(policy: dict, publisher: str) -> Path:
    registry = policy.get("registry") or {}
    configured = registry.get("publisherStatePath") or "/var/lib/cluster-identity/publisher-state"
    return Path(configured) / f"{publisher}.json"


def build_snapshot(
    registry: Path,
    snapshot_dir: Path,
    policy: dict,
    publisher: str,
    signing_key: Path,
) -> dict:
    trusted = (policy.get("trustedLeaders") or {}).get(publisher) or {}
    public_key = trusted.get("publicSigningKey")
    if not public_key:
        raise ValueError(f"publisher {publisher!r} is not a trusted leader")
    if key_fingerprint(public_key) != key_fingerprint(public_key_from_private(signing_key)):
        raise ValueError(f"signing key does not match trusted leader {publisher!r}")

    reconcile(registry, None, policy)
    state_path = publisher_state_path(policy, publisher)
    publisher_state = read_json(state_path, {}) or {}
    root_sequence = int(publisher_state.get("rootSequence", 0)) + 1

    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True)
    _copy_content(registry, snapshot_dir)
    policy_path = snapshot_dir / "policy" / "leader-policy.json"
    write_json(policy_path, leader_policy_document(policy, publisher, signing_key))

    root = {
        "schema": "cluster.identity.root.v1",
        "clusterId": cluster_id(policy),
        "publisher": publisher,
        "publisherKeyId": key_fingerprint(public_key),
        "rootSequence": root_sequence,
        "previousRootCid": publisher_state.get("rootCid"),
        "eventChainTip": leader_chain_tip(snapshot_dir, publisher),
        "createdAt": now_utc(),
        "content": _content_index(snapshot_dir),
    }
    root["signature"] = sign_record(root, signing_key)
    write_json(snapshot_dir / "root.json", root)

    failures = validate_registry(snapshot_dir, policy)
    if failures:
        raise ValueError("snapshot verification failed:\n" + "\n".join(f"- {failure}" for failure in failures))
    return root


def publish_snapshot(
    registry: Path,
    snapshot_dir: Path,
    policy: dict,
    publisher: str,
    signing_key: Path,
) -> dict:
    leader = (policy.get("trustedLeaders") or {}).get(publisher) or {}
    expected_ipns_name = leader.get("ipnsName")
    if not expected_ipns_name:
        raise ValueError(f"trusted leader {publisher!r} has no enrolled IPNS name")
    ipfs_config = (policy.get("registry") or {}).get("ipfs") or {}
    key_name = ipfs_config.get("keyName") or f"cluster-identity-{publisher}"

    root = build_snapshot(registry, snapshot_dir, policy, publisher, signing_key)
    root_cid = ipfs.add_directory(policy, snapshot_dir)
    ipfs.pin(policy, root_cid)
    publish_output = ipfs.publish_name(policy, key_name, expected_ipns_name, root_cid)
    state = {
        "schema": "cluster.identity.publisher-state.v1",
        "clusterId": cluster_id(policy),
        "publisher": publisher,
        "rootSequence": root["rootSequence"],
        "rootCid": root_cid,
        "previousRootCid": root["previousRootCid"],
        "ipnsName": expected_ipns_name,
        "publishedAt": now_utc(),
    }
    _atomic_write(publisher_state_path(policy, publisher), state)
    try:
        pubsub_result = announcements.publish_announcement(
            policy,
            state,
            root,
            signing_key,
        )
    except Exception as error:
        pubsub_result = {
            "status": "failed",
            "reason": str(error),
        }
    try:
        onion_result = onion.publish_mirror(
            policy,
            state,
            root,
            snapshot_dir,
            signing_key,
        )
    except Exception as error:
        onion_result = {
            "status": "failed",
            "reason": str(error),
        }
    return state | {
        "ipnsResult": publish_output,
        "pubsub": pubsub_result,
        "onionMirror": onion_result,
    }
