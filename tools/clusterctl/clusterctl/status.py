import os
import shutil
import tempfile
from pathlib import Path

from . import ipfs
from .events import now_utc, read_json, write_json
from .registry import cluster_id
from .signing import key_fingerprint, public_key_from_private, sign_record, verify_signature


STATUS_SCHEMA = "cluster.identity.node-status.v1"


def default_status_key_name(node: str) -> str:
    return f"cluster-identity-status-{node}"


def ensure_status_key(policy: dict, key_name: str) -> str:
    keys = ipfs.key_names(policy, attempts=180, retry_delay=1.0)
    if key_name in keys:
        return keys[key_name]
    ipns_name = ipfs.generate_key(policy, key_name)
    keys = ipfs.key_names(policy)
    if keys.get(key_name) != ipns_name:
        raise RuntimeError(f"Kubo did not retain generated IPNS key {key_name!r}")
    return ipns_name


def status_publisher_record(policy: dict, node: str) -> dict:
    return ((policy.get("statusPublishers") or {}).get(node)) or {}


def status_key_name(policy: dict, node: str, explicit: str | None = None) -> str:
    configured = status_publisher_record(policy, node).get("keyName")
    return explicit or configured or default_status_key_name(node)


def status_ipns_name(policy: dict, node: str, explicit: str | None = None) -> str:
    configured = status_publisher_record(policy, node).get("ipnsName")
    value = explicit or configured
    if not value:
        raise ValueError(f"node {node!r} has no enrolled status IPNS name")
    return value


def _node_services(path: Path, node: str) -> dict:
    state = read_json(path, {}) or {}
    return ((state.get("nodes") or {}).get(node)) or {}


def _public_service_record(record: dict, state: str) -> dict:
    result = {
        "generation": int(record.get("generation", 0)),
        "state": record.get("state") or state,
    }
    public = record.get("public") or {}
    if public:
        result["public"] = public
    return result


def _service_map(materialized_path: Path, node: str, name: str) -> dict:
    return {
        service: _public_service_record(record, name.removesuffix(".json"))
        for service, record in sorted(
            _node_services(materialized_path / name, node).items()
        )
    }


def _service_tree(materialized_path: Path, name: str) -> dict:
    state = read_json(materialized_path / name, {}) or {}
    return {
        node: {
            service: _public_service_record(record, name.removesuffix(".json"))
            for service, record in sorted((services or {}).items())
        }
        for node, services in sorted((state.get("nodes") or {}).items())
    }


def _node_conflicts(materialized_path: Path, node: str) -> dict:
    conflicts = read_json(materialized_path / "conflicts.json", {}) or {}
    subjects = conflicts.get("subjects") or {}
    prefix = f"{node}/"
    return {
        subject: value
        for subject, value in sorted(subjects.items())
        if subject.startswith(prefix)
    }


def _checkpoint_heads(local_state_path: Path) -> dict:
    checkpoint = read_json(local_state_path / "checkpoint.json", {}) or {}
    heads = checkpoint.get("heads") or {}
    return {
        leader: {
            key: value
            for key, value in (head or {}).items()
            if key in {"cid", "rootSequence", "acceptedAt"}
        }
        for leader, head in sorted(heads.items())
    }


def build_status_record(
    policy: dict,
    node: str,
    materialized_path: Path,
    local_state_path: Path,
    signing_key: Path,
    expected_ipns_name: str,
) -> dict:
    public_key = public_key_from_private(signing_key)
    rotations = read_json(materialized_path / "rotations.json", {}) or {}
    record = {
        "schema": STATUS_SCHEMA,
        "clusterId": cluster_id(policy),
        "node": node,
        "statusIpnsName": expected_ipns_name,
        "observedAt": now_utc(),
        "implementedServices": _service_map(materialized_path, node, "active.json"),
        "acceptedServices": {
            "nodes": _service_tree(materialized_path, "active.json"),
        },
        "stagedServices": _service_map(materialized_path, node, "staged.json"),
        "deprecatedServices": _service_map(materialized_path, node, "deprecated.json"),
        "burnedServices": _service_map(materialized_path, node, "burned.json"),
        "rotations": rotations.get("rotations", {}),
        "conflicts": _node_conflicts(materialized_path, node),
        "acceptedRegistryHeads": _checkpoint_heads(local_state_path),
        "signedByNode": {
            "type": "ssh-host-ed25519",
            "publicKey": public_key,
            "keyId": key_fingerprint(public_key),
        },
    }
    record["signature"] = sign_record(record, signing_key)
    return record


def _atomic_status_dir(status_dir: Path, record: dict) -> None:
    status_dir.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{status_dir.name}-", dir=status_dir.parent))
    try:
        write_json(work / "status.json", record)
        if status_dir.exists():
            shutil.rmtree(status_dir)
        os.replace(work, status_dir)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def publish_status(
    policy: dict,
    node: str,
    materialized_path: Path,
    local_state_path: Path,
    status_dir: Path,
    signing_key: Path,
    key_name: str,
    expected_ipns_name: str,
) -> dict:
    record = build_status_record(
        policy,
        node,
        materialized_path,
        local_state_path,
        signing_key,
        expected_ipns_name,
    )
    _atomic_status_dir(status_dir, record)
    root_cid = ipfs.add_directory(policy, status_dir)
    ipfs.pin(policy, root_cid)
    publish_output = ipfs.publish_name(policy, key_name, expected_ipns_name, root_cid)
    state = {
        "schema": "cluster.identity.node-status-publisher-state.v1",
        "clusterId": cluster_id(policy),
        "node": node,
        "statusIpnsName": expected_ipns_name,
        "statusCid": root_cid,
        "publishedAt": now_utc(),
    }
    write_json(local_state_path / "status-publish.json", state)
    return state | {"ipnsResult": publish_output}


def validate_status_record(
    policy: dict,
    node: str,
    record: dict,
    expected_ipns_name: str,
) -> tuple[bool, str]:
    if record.get("schema") != STATUS_SCHEMA:
        return False, "status schema does not match"
    if record.get("clusterId") != cluster_id(policy):
        return False, "status clusterId does not match"
    if record.get("node") != node:
        return False, "status node does not match"
    if record.get("statusIpnsName") != expected_ipns_name:
        return False, "status IPNS name does not match"
    expected_key = status_publisher_record(policy, node).get("publicSigningKey")
    signed_by_node = record.get("signedByNode") or {}
    record_key = (
        signed_by_node.get("publicKey") if isinstance(signed_by_node, dict) else None
    )
    if expected_key and (
        not record_key or key_fingerprint(record_key) != key_fingerprint(expected_key)
    ):
        return False, "status signing key does not match policy"
    return verify_signature(record, {})


def fetch_status_record(
    policy: dict,
    node: str,
    cache_dir: Path,
) -> dict:
    expected_ipns_name = status_ipns_name(policy, node)
    cid = ipfs.resolve_name(policy, expected_ipns_name)
    destination = cache_dir / node / cid
    ipfs.fetch_directory(policy, cid, destination, required_file="status.json")
    record = read_json(destination / "status.json", {}) or {}
    ok, reason = validate_status_record(policy, node, record, expected_ipns_name)
    if not ok:
        raise ValueError(reason)
    record["statusCid"] = cid
    return record
