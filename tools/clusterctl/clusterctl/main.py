import argparse
import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from . import (
    announcements,
    bundles,
    deploy,
    follower,
    install,
    ipfs,
    notify,
    onion,
    registry,
    snapshot,
    status,
    transport,
    update,
)
from .events import VALID_STATES, new_event_id, now_utc, read_json, write_json
from .execution import (
    ExecutionMode,
    Privilege,
    execution_mode,
    prepare_invocation,
    privileged_command,
    run as run_command,
)
from .signing import SIGNATURE_NAMESPACE, key_fingerprint, sign_record, signature_value

DEFAULT_REGISTRY = Path("/var/lib/cluster-identity/registry")
DEFAULT_OUT = Path("/run/cluster-identity")
DEFAULT_POLICY = Path("/etc/cluster-identity/policy.json")
DEFAULT_SNAPSHOT = Path("/var/lib/cluster-identity/publisher/snapshot")
DEFAULT_HOST_AGE_TARGET_PATH = "/var/lib/cluster-identity/age/host.agekey"

YGGDRASIL_DISCOVERY_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail

keys_path=/var/lib/yggdrasil/keys.json
keys_dir=$(dirname "$keys_path")
filter_expr='to_entries|map(select(.key|endswith("Key")))|from_entries'

ensure_keys() {
  if [ -e "$keys_path" ]; then
    return 0
  fi

  install -d -m 700 "$keys_dir"

  if command -v yggdrasil >/dev/null 2>&1; then
    if command -v jq >/dev/null 2>&1; then
      yggdrasil -genconf -json | jq "$filter_expr" > "$keys_path"
    else
      nix shell nixpkgs#jq -c bash -lc \
        "yggdrasil -genconf -json | jq '$filter_expr' > '$keys_path'"
    fi
  else
    nix shell nixpkgs#jq nixpkgs#yggdrasil -c bash -lc \
      "yggdrasil -genconf -json | jq '$filter_expr' > '$keys_path'"
  fi

  chmod 600 "$keys_path"
}

read_public_key() {
  if command -v yggdrasil >/dev/null 2>&1; then
    yggdrasil -useconffile "$keys_path" -publickey
  else
    nix shell nixpkgs#yggdrasil -c yggdrasil -useconffile "$keys_path" -publickey
  fi
}

read_address() {
  if command -v yggdrasil >/dev/null 2>&1; then
    yggdrasil -useconffile "$keys_path" -address
  else
    nix shell nixpkgs#yggdrasil -c yggdrasil -useconffile "$keys_path" -address
  fi
}

ensure_keys
public_key="$(read_public_key)"
address="$(read_address)"

printf '{"publicKey":"%s","address":"%s"}\n' "$public_key" "$address"
"""

IDENTITY_SERVICE_ORDER = [
    "host-age",
    "ipns-publisher",
    "onion-mirror",
    "status-ipns",
    "leader-user-ssh",
    "ssh-host",
    "yggdrasil",
    "radicle",
    "git-annex",
]

GUARDED_STALE_BURN_SERVICES = {
    "host-age",
    "ipns-publisher",
    "status-ipns",
    "leader-user-ssh",
    "ssh-host",
}

STATE_ABBREVIATIONS = {
    "planned": "p",
    "staged": "s",
    "private-delivered": "pd",
    "node-received": "nr",
    "node-activated": "na",
    "leader-verified": "lv",
    "active": "a",
    "active-acknowledged": "aa",
    "active-unconfirmed": "au",
    "deprecated": "d",
    "removed": "rm",
    "burned": "b",
}

DEFAULT_MATRIX_BURN_LIMIT = 2
DEFAULT_STATUS_CACHE = Path("/var/lib/cluster-identity/status-cache")

IDENTITY_SOURCE_FILES = {
    "ipns-publisher": "inventory/identity-services/ipns-publisher.nix",
    "onion-mirror": "inventory/identity-services/onion-mirror.nix",
    "status-ipns": "inventory/identity-services/status-ipns.nix",
    "leader-user-ssh": "inventory/identity-services/leader-user-ssh.nix",
    "yggdrasil": "inventory/identity-services/yggdrasil.nix",
    "ssh-host": "inventory/identity-services/ssh-host.nix",
    "radicle": "inventory/identity-services/radicle.nix",
    "git-annex": "inventory/identity-services/git-annex.nix",
}


def load_policy(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return read_json(path, {}) or {}


def leader_key(policy: dict, leader: str) -> str:
    leaders = policy.get("trustedLeaders", {})
    key = (leaders.get(leader) or {}).get("publicSigningKey")
    if not key:
        raise ValueError(f"no trusted signing key for leader {leader!r}")
    return key


def signing_key_path(policy: dict, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    rules = policy.get("policy", policy)
    configured = policy.get("signingKeyPath") or rules.get("signingKeyPath")
    if configured:
        return Path(configured)
    raise ValueError(
        "no signing key configured; pass --signing-key or set policy.signingKeyPath"
    )


def node_signing_key_path(policy: dict, explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    configured = policy.get("receiptSigningKeyPath")
    return Path(configured or "/etc/ssh/ssh_host_ed25519_key")


def attach_signature(
    record: dict, key_path: Path | None, provided: str | None, policy: dict
) -> dict:
    if provided:
        key_id = record.get("leaderKeyId") or record.get("publisherKeyId")
        if not key_id and isinstance(record.get("signedByNode"), dict):
            key_id = record["signedByNode"].get("keyId")
        if not key_id:
            raise ValueError("cannot attach a provided signature without a keyId")
        record["signature"] = {
            "type": "openssh",
            "namespace": SIGNATURE_NAMESPACE,
            "keyId": key_id,
            "value": provided,
        }
        return record
    path = signing_key_path(policy, key_path)
    if not path.exists():
        raise ValueError(f"signing key does not exist: {path}")
    record["signature"] = sign_record(record, path)
    return record


def commit(registry_path: Path, message: str, enabled: bool = True) -> None:
    if enabled:
        transport.git_commit_if_possible(registry_path, message)


def registry_needs_v1_reseed(registry_path: Path) -> bool:
    events_path = registry_path / "events"
    if not events_path.exists():
        return False
    if any(path.is_file() for path in events_path.glob("*.json")):
        return True
    return any(
        event.get("schema")
        not in {
            registry.IDENTITY_EVENT_SCHEMA,
            registry.SUPERSEDENCE_SCHEMA,
            registry.ROTATION_SCHEMA,
        }
        for _path, event in registry.load_events(registry_path)
    )


def cmd_registry_ensure_v1(args) -> int:
    registry_path = args.registry
    if registry_needs_v1_reseed(registry_path):
        timestamp = now_utc().replace(":", "").replace("-", "")
        archive_path = registry_path.parent / f"{registry_path.name}-pre-v1-{timestamp}"
        suffix = 1
        while archive_path.exists():
            archive_path = (
                registry_path.parent
                / f"{registry_path.name}-pre-v1-{timestamp}-{suffix}"
            )
            suffix += 1
        shutil.move(str(registry_path), str(archive_path))
        print(f"Archived incompatible pre-v1 registry at {archive_path}")
    registry.init_registry(registry_path)
    commit(registry_path, "identity registry v1 init", not args.no_commit)
    print(f"Registry v1 ready at {registry_path}")
    return 0


def cmd_registry_validate(args) -> int:
    failures = registry.validate_registry(args.registry, load_policy(args.policy))
    if failures:
        print("Registry validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Registry validation passed")
    return 0


def cmd_registry_reconcile(args) -> int:
    registry.reconcile(args.registry, args.out, load_policy(args.policy))
    print(f"Reconciled {args.registry}")
    if args.out:
        print(f"Materialized state into {args.out}")
    return 0


def cmd_registry_fetch_ipfs(args) -> int:
    policy = load_policy(args.policy)
    registry_config = dict(policy.get("registry") or {})
    if args.cache_dir is not None:
        registry_config["followerCachePath"] = str(args.cache_dir)
    if args.accepted_registry is not None:
        registry_config["acceptedRegistryPath"] = str(args.accepted_registry)
    policy["registry"] = registry_config
    report = follower.fetch_and_materialize(policy, args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def cmd_registry_notify(args) -> int:
    targets = args.target
    if not targets:
        bootstrap = transport.host_bootstrap(args.flake)
        targets = sorted(bootstrap.keys())
    notify.notify_targets(targets, args.out, args.flake)
    print(f"Notification attempted for: {', '.join(targets)}")
    return 0


def cmd_registry_listen_pubsub(args) -> int:
    policy = load_policy(args.policy)
    announcements.listen_and_trigger(policy, args.trigger_unit)
    return 0


def cmd_registry_status(args) -> int:
    policy = load_policy(args.policy)
    local_state = registry.local_state_path(policy)
    print(f"Registry: {args.registry}")
    print(f"Materialized: {args.out}")
    print(f"Local state: {local_state}")
    for name in ["active.json", "staged.json", "deprecated.json", "burned.json"]:
        state = read_json(args.out / name, None)
        if state is None:
            state = read_json(args.registry / "state" / name, None)
        if args.node and isinstance(state, dict):
            state = {
                "nodes": {args.node: (state.get("nodes") or {}).get(args.node, {})}
            }
        count = 0
        if isinstance(state, dict):
            count = sum(
                len(services) for services in (state.get("nodes") or {}).values()
            )
        print(f"{name}: {count} records")
    conflicts = read_json(args.out / "conflicts.json", None)
    if conflicts is None:
        conflicts = read_json(args.registry / "state" / "conflicts.json", {})
    conflict_count = (
        len(conflicts.get("subjects") or {}) if isinstance(conflicts, dict) else 0
    )
    print(f"conflicts: {conflict_count}")

    checkpoint = read_json(local_state / "checkpoint.json", {}) or {}
    print("Accepted IPNS heads:")
    heads = checkpoint.get("heads") or {}
    if not heads:
        print("  none")
    for leader, head in sorted(heads.items()):
        print(
            f"  {leader}: sequence={head.get('rootSequence', '?')} "
            f"cid={head.get('cid', '?')} accepted={head.get('acceptedAt', '?')}"
        )

    fetch_status = read_json(local_state / "fetch-status.json", {}) or {}
    print(f"Last fetch: {fetch_status.get('checkedAt', 'never')}")
    for leader, result in sorted((fetch_status.get("leaders") or {}).items()):
        detail = (
            result.get("cid") or result.get("retainedCid") or result.get("reason") or ""
        )
        print(f"  {leader}: {result.get('status', 'unknown')} {detail}".rstrip())

    pubsub_status = read_json(local_state / "pubsub-status.json", {}) or {}
    connection_state = pubsub_status.get("connectionState", "not started")
    last_result = pubsub_status.get("lastResult", "no messages observed")
    print(f"PubSub listener: {connection_state}; {last_result}")
    if pubsub_status:
        print(
            "  "
            f"accepted={pubsub_status.get('accepted', 0)} "
            f"ignored={pubsub_status.get('ignored', 0)} "
            f"rejected={pubsub_status.get('rejected', 0)} "
            f"topic={pubsub_status.get('topic', '?')}"
        )
    return 0


def _publisher(policy: dict, explicit: str | None) -> str:
    return explicit or policy.get("hostName") or socket.gethostname()


def _snapshot_path(policy: dict, explicit: Path | None) -> Path:
    configured = (policy.get("registry") or {}).get("snapshotPath")
    return explicit or Path(configured or DEFAULT_SNAPSHOT)


def cmd_registry_snapshot(args) -> int:
    policy = load_policy(args.policy)
    publisher = _publisher(policy, args.publisher)
    root = snapshot.build_snapshot(
        args.registry,
        _snapshot_path(policy, args.snapshot_dir),
        policy,
        publisher,
        signing_key_path(policy, args.signing_key),
    )
    print(json.dumps(root, indent=2, sort_keys=True))
    return 0


def cmd_registry_publish_ipfs(args) -> int:
    policy = load_policy(args.policy)
    publisher = _publisher(policy, args.publisher)
    state = snapshot.publish_snapshot(
        args.registry,
        _snapshot_path(policy, args.snapshot_dir),
        policy,
        publisher,
        signing_key_path(policy, args.signing_key),
    )
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


def cmd_registry_ipns_key_ensure(args) -> int:
    policy = load_policy(args.policy)
    publisher = _publisher(policy, args.publisher)
    leader = (policy.get("trustedLeaders") or {}).get(publisher) or {}
    expected_name = args.expected_name or leader.get("ipnsName")
    if not expected_name:
        raise ValueError(f"trusted leader {publisher!r} has no enrolled IPNS name")
    config = (policy.get("registry") or {}).get("ipfs") or {}
    key_name = args.key_name or config.get("keyName") or f"cluster-identity-{publisher}"
    actual = ipfs.ensure_ipns_key(policy, key_name, args.key_file, expected_name)
    print(f"{key_name} {actual}")
    return 0


def cmd_registry_status_ipns_key_ensure(args) -> int:
    policy = load_policy(args.policy)
    node = args.node or policy.get("hostName") or socket.gethostname()
    key_name = status.status_key_name(policy, node, args.key_name)
    if args.key_file is not None:
        expected_name = status.status_ipns_name(policy, node, args.expected_name)
        ipns_name = ipfs.ensure_ipns_key(policy, key_name, args.key_file, expected_name)
    else:
        ipns_name = status.ensure_status_key(policy, key_name)
    print(f"{key_name} {ipns_name}")
    return 0


def cmd_registry_publish_status(args) -> int:
    policy = load_policy(args.policy)
    node = args.node or policy.get("hostName") or socket.gethostname()
    registry_config = policy.get("registry") or {}
    local_state = registry.local_state_path(policy)
    status_dir = args.status_dir or Path(
        registry_config.get("statusPublisherPath")
        or "/var/lib/cluster-identity/status-publisher/status"
    )
    key_name = status.status_key_name(policy, node, args.key_name)
    expected_name = status.status_ipns_name(policy, node, args.expected_name)
    state = status.publish_status(
        policy,
        node,
        args.out,
        local_state,
        status_dir,
        node_signing_key_path(policy, args.signing_key),
        key_name,
        expected_name,
    )
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


def prepare_event(
    registry_path: Path,
    event: dict,
    policy: dict,
    leader_public_key: str,
    signing_key: Path | None,
    provided_signature: str | None,
) -> Path:
    event["clusterId"] = registry.cluster_id(policy)
    if not event["clusterId"]:
        raise ValueError("clusterId is missing from registry policy")
    event["leaderKeyId"] = key_fingerprint(leader_public_key)
    event.pop("leaderKey", None)
    event.pop("signature", None)
    registry.ensure_public_fingerprint(event)
    registry.finalize_event(registry_path, event)
    attach_signature(event, signing_key, provided_signature, policy)
    path = registry.canonical_event_path(registry_path, event)
    write_json(path, event)
    return path


def public_from_identity_record(record: dict) -> dict:
    public = dict(record.get("public") or {})
    source_timestamp = record.get("sourceTimestamp") or record.get("keyGeneratedAt")
    if source_timestamp:
        public.setdefault("sourceTimestamp", source_timestamp)
    key_generated_at = record.get("keyGeneratedAt")
    if key_generated_at:
        public.setdefault("keyGeneratedAt", key_generated_at)
    return public


def private_delivery_from_identity_record(record: dict) -> dict | None:
    private = dict(record.get("private") or {})
    if not private:
        return None
    delivery = {
        "status": private.get("status", "planned"),
        "recipientHost": private.get("recipientHost"),
        "targetPath": private.get("targetPath"),
        "sopsPath": private.get("sopsPath"),
        "bundleManifest": private.get("bundleManifest"),
        "bundlePath": private.get("bundlePath"),
        "recipientFingerprint": private.get("recipientFingerprint"),
        "sourceTimestamp": record.get("sourceTimestamp")
        or record.get("keyGeneratedAt"),
        "requiresReceipt": bool(private.get("requiresReceipt", False)),
    }
    return {key: value for key, value in delivery.items() if value is not None}


def flake_identity_records(
    inventory: dict, services: set[str] | None = None, nodes: set[str] | None = None
):
    identity_services = (inventory.get("identities") or {}).get("services") or {}
    for service in sorted(identity_services.keys()):
        if services and service not in services:
            continue
        service_records = identity_services.get(service) or {}
        for node in sorted(service_records.keys()):
            if nodes and node not in nodes:
                continue
            requirement = (
                identity_requirements_for_host(inventory, node).get(service) or {}
            )
            if requirement.get("registryPublish") is False:
                continue
            record = service_records.get(node) or {}
            public = public_from_identity_record(record)
            if not public:
                continue
            private_delivery = private_delivery_from_identity_record(record)
            generation = record.get("generation", 1)
            state = record.get("state", "staged")
            yield node, service, record, public, private_delivery, generation, state


def split_cli_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    expanded: list[str] = []
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                expanded.append(item)
    return expanded


def normalize_filter_values(values: list[str] | None) -> set[str] | None:
    expanded = split_cli_values(values)
    if not expanded or "all" in expanded:
        return None
    return set(expanded)


def resolve_hosts_arg(values: list[str], inventory: dict) -> list[str]:
    available = sorted((inventory.get("hosts") or {}).keys())
    selected = split_cli_values(values)
    if not selected or "all" in selected:
        return available
    return selected


def inventory_hosts(
    inventory: dict, nodes: set[str] | None = None
) -> list[tuple[str, dict]]:
    hosts = inventory.get("hosts") or {}
    selected = []
    for node in sorted(hosts.keys()):
        if nodes and node not in nodes:
            continue
        selected.append((node, hosts.get(node) or {}))
    return selected


def service_sort_key(service: str) -> tuple[int, str]:
    try:
        return (IDENTITY_SERVICE_ORDER.index(service), service)
    except ValueError:
        return (len(IDENTITY_SERVICE_ORDER), service)


def identity_requirements_for_host(inventory: dict, node: str) -> dict:
    requirements = inventory.get("identityRequirements") or {}
    return ((requirements.get("byHost") or {}).get(node)) or {}


def identity_record_cell(record: dict) -> str:
    generation = record.get("generation")
    generation_text = generation if isinstance(generation, int) else "?"
    state = record.get("displayState") or record.get("state") or "unknown"
    state_text = STATE_ABBREVIATIONS.get(state, state[:2])
    return f"g{generation_text}/{state_text}"


def live_identity_records(out: Path | None) -> dict[str, dict[str, list[dict]]]:
    if out is None:
        return {}
    records: dict[str, dict[str, list[dict]]] = {}
    for filename in ["active.json", "staged.json", "deprecated.json", "burned.json"]:
        state_path = out / filename
        if not state_path.exists():
            continue
        nodes = read_json(state_path, {}).get("nodes") or {}
        for node, services in nodes.items():
            for service, record in (services or {}).items():
                records.setdefault(node, {}).setdefault(service, []).append(record)
    for services in records.values():
        for service_records in services.values():
            service_records.sort(
                key=lambda record: (
                    record.get("generation")
                    if isinstance(record.get("generation"), int)
                    else -1,
                    record.get("state") or "",
                )
            )
    return records


def live_identity_cell(records: list[dict]) -> str | None:
    if not records:
        return None
    return ",".join(identity_record_cell(record) for record in records)


def identity_records_sort_key(record: dict) -> tuple[int, str, str]:
    generation = identity_generation(record)
    return (
        generation if generation is not None else -1,
        record.get("createdAt") or "",
        record.get("eventId") or "",
    )


def records_with_burn_limit(records: list[dict], burn_limit: int | None) -> list[dict]:
    if burn_limit is None or burn_limit < 0:
        return records
    burned_records = [record for record in records if record.get("state") == "burned"]
    if len(burned_records) <= burn_limit:
        return records
    kept_burns = set()
    if burn_limit > 0:
        kept_burns = {
            id(record)
            for record in sorted(burned_records, key=identity_records_sort_key)[
                -burn_limit:
            ]
        }
    return [
        record
        for record in records
        if record.get("state") != "burned" or id(record) in kept_burns
    ]


def records_after_generation_burns(records: list[dict]) -> list[dict]:
    burned_by_generation = {
        generation: record
        for record in records
        if record.get("state") == "burned"
        for generation in [identity_generation(record)]
        if generation is not None
    }
    if not burned_by_generation:
        return records

    resolved = []
    emitted_burns: set[int] = set()
    for record in records:
        generation = identity_generation(record)
        if generation not in burned_by_generation:
            resolved.append(record)
            continue
        burn_record = burned_by_generation[generation]
        if generation not in emitted_burns and record is burn_record:
            resolved.append(record)
            emitted_burns.add(generation)
    return resolved


def identity_record_matches(service: str, expected: dict, observed: dict | None) -> bool:
    if not observed:
        return False
    if identity_generation(expected) != identity_generation(observed):
        return False
    expected_fingerprint = registry.public_identity_fingerprint(
        service, expected.get("public") or {}
    )
    observed_fingerprint = registry.public_identity_fingerprint(
        service, observed.get("public") or {}
    )
    if expected_fingerprint:
        return observed_fingerprint == expected_fingerprint
    return True


def accepted_status_record(status_record: dict, node: str, service: str) -> dict | None:
    return (
        ((status_record.get("acceptedServices") or {}).get("nodes") or {})
        .get(node, {})
        .get(service)
    )


def annotate_identity_record_status(
    record: dict | None,
    *,
    node: str,
    service: str,
    status_records: dict[str, dict] | None,
) -> dict | None:
    if record is None:
        return None
    if record.get("state") != "active":
        return record
    if status_records is None:
        return record
    annotated = dict(record)
    if not status_records:
        annotated["displayState"] = "active-unconfirmed"
        annotated["statusAcknowledgement"] = {
            "targetActive": False,
            "reachablePeers": [],
            "agreeingPeers": [],
            "disagreeingPeers": [],
        }
        return annotated

    target_status = status_records.get(node)
    target_record = (
        (target_status.get("implementedServices") or {}).get(service)
        if target_status
        else None
    )
    target_active = identity_record_matches(service, record, target_record)
    reachable_peers = sorted(
        peer_node
        for peer_node in status_records
        if peer_node != node
    )
    agreeing_peers = []
    disagreeing_peers = []
    for peer_node in reachable_peers:
        peer_record = accepted_status_record(status_records[peer_node], node, service)
        if identity_record_matches(service, record, peer_record):
            agreeing_peers.append(peer_node)
        else:
            disagreeing_peers.append(peer_node)

    if not target_active:
        display_state = "active-unconfirmed"
    elif reachable_peers and not disagreeing_peers:
        display_state = "active-acknowledged"
    else:
        display_state = "active"
    annotated["displayState"] = display_state
    annotated["statusAcknowledgement"] = {
        "targetActive": target_active,
        "reachablePeers": reachable_peers,
        "agreeingPeers": agreeing_peers,
        "disagreeingPeers": disagreeing_peers,
    }
    return annotated


def annotate_identity_records_status(
    records: list[dict],
    *,
    node: str,
    service: str,
    status_records: dict[str, dict] | None,
) -> list[dict]:
    return [
        annotated
        for record in records
        for annotated in [
            annotate_identity_record_status(
                record, node=node, service=service, status_records=status_records
            )
        ]
        if annotated is not None
    ]


def identity_generation(record: dict | None) -> int | None:
    if not record:
        return None
    generation = record.get("generation")
    return generation if isinstance(generation, int) else None


def registry_identity_generations(
    registry_path: Path | None, node: str, service: str
) -> list[int]:
    if registry_path is None or not registry_path.exists():
        return []
    generations: list[int] = []
    try:
        events = registry.identity_events(registry.load_events(registry_path))
    except Exception as error:
        print(
            f"Warning: could not read live identity generations from "
            f"{registry_path}: {error}",
            file=sys.stderr,
        )
        return []
    for _path, event in events:
        subject = event.get("subject") or {}
        if subject.get("node") != node or subject.get("service") != service:
            continue
        generation = identity_generation(event)
        if generation is not None:
            generations.append(generation)
    return generations


def known_identity_generation(
    current: dict | None,
    registry_path: Path | None,
    policy_path: Path | None,
    out: Path | None,
    node: str,
    service: str,
) -> int:
    generations = []
    current_generation = identity_generation(current)
    if current_generation is not None:
        generations.append(current_generation)

    for record in live_identity_records(out).get(node, {}).get(service, []):
        generation = identity_generation(record)
        if generation is not None:
            generations.append(generation)

    generations.extend(registry_identity_generations(registry_path, node, service))

    if policy_path is not None:
        try:
            accepted = follower.accepted_registry_path(load_policy(policy_path))
            generations.extend(registry_identity_generations(accepted, node, service))
        except Exception as error:
            print(
                f"Warning: could not read accepted live registry generations: {error}",
                file=sys.stderr,
            )

    return max(generations) if generations else 0


def previous_same_leader_burn_targets(
    *,
    registry_path: Path,
    observed_registry_path: Path | None,
    leader: str,
    node: str,
    service: str,
    generation: int,
    new_public: dict,
) -> list[dict]:
    new_fingerprint = registry.public_identity_fingerprint(service, new_public)
    burned: set[tuple[int, str]] = set()
    targets: dict[tuple[int, str], dict] = {}

    for source in [registry_path, observed_registry_path]:
        if source is None or not source.exists():
            continue
        try:
            records = registry.load_events(source)
        except Exception as error:
            print(
                f"Warning: could not inspect old same-leader identities in "
                f"{source}: {error}",
                file=sys.stderr,
            )
            continue
        for _path, event in registry.identity_events(records):
            subject = event.get("subject") or {}
            event_generation = identity_generation(event)
            if subject.get("node") != node or subject.get("service") != service:
                continue
            if event_generation is None or event_generation >= generation:
                continue
            if event.get("state") == "burned":
                fingerprint = (event.get("burned") or {}).get("fingerprint")
                if isinstance(fingerprint, str):
                    burned.add((event_generation, fingerprint))
                continue
            if event.get("leader") != leader:
                continue
            fingerprint = registry.public_identity_fingerprint(
                service, event.get("public") or {}
            )
            if not fingerprint or fingerprint == new_fingerprint:
                continue
            targets[(event_generation, fingerprint)] = event

    return [
        event
        for key, event in sorted(
            targets.items(), key=lambda item: (item[0][0], item[0][1])
        )
        if key not in burned
    ]


def same_leader_stale_burn_targets(
    *,
    registry_path: Path,
    observed_registry_path: Path | None,
    leader: str,
    desired: dict[tuple[str, str], dict],
    include_guarded: bool,
) -> list[tuple[dict, str]]:
    burned: set[tuple[str, str, int, str]] = set()
    targets: dict[tuple[str, str, int, str], tuple[dict, str]] = {}

    for source in [registry_path, observed_registry_path]:
        if source is None or not source.exists():
            continue
        try:
            records = registry.load_events(source)
        except Exception as error:
            print(
                f"Warning: could not inspect stale live identities in "
                f"{source}: {error}",
                file=sys.stderr,
            )
            continue
        for _path, event in registry.identity_events(records):
            subject = event.get("subject") or {}
            node = subject.get("node")
            service = subject.get("service")
            event_generation = identity_generation(event)
            if not isinstance(node, str) or not isinstance(service, str):
                continue
            if event_generation is None:
                continue
            if event.get("state") == "burned":
                fingerprint = (event.get("burned") or {}).get("fingerprint")
                if isinstance(fingerprint, str):
                    burned.add((node, service, event_generation, fingerprint))
                continue
            if event.get("leader") != leader:
                continue
            fingerprint = registry.public_identity_fingerprint(
                service, event.get("public") or {}
            )
            if not fingerprint:
                continue
            desired_record = desired.get((node, service))
            reason = None
            if desired_record is None:
                if service in GUARDED_STALE_BURN_SERVICES and not include_guarded:
                    continue
                reason = "publishing leader no longer has this identity in inventory"
            else:
                desired_generation = desired_record["generation"]
                desired_fingerprint = registry.public_identity_fingerprint(
                    service, desired_record["public"]
                )
                if (
                    event_generation == desired_generation
                    and fingerprint == desired_fingerprint
                ):
                    continue
                if fingerprint == desired_fingerprint:
                    continue
                if service in GUARDED_STALE_BURN_SERVICES and not include_guarded:
                    continue
                if event_generation < desired_generation:
                    reason = "publishing leader inventory rotated a newer generation"
                elif event_generation > desired_generation:
                    reason = "publishing leader inventory does not imply this newer generation"
                else:
                    reason = "publishing leader inventory has a different identity for this generation"
            targets[(node, service, event_generation, fingerprint)] = (event, reason)

    return [
        target
        for key, target in sorted(
            targets.items(), key=lambda item: (item[0][0], item[0][1], item[0][2])
        )
        if key not in burned
    ]


def append_burn_event(
    *,
    registry_path: Path,
    policy: dict,
    leader: str,
    leader_key_arg: str | None,
    node: str,
    service: str,
    generation: int,
    fingerprint: str,
    reason: str,
    signing_key: Path | None,
) -> Path:
    leader_public_key = leader_key_arg or leader_key(policy, leader)
    event = {
        "schema": "cluster.identity.event.v1",
        "eventId": new_event_id("burn"),
        "leader": leader,
        "policyGeneration": int(
            (policy.get("policy") or policy).get("policyGeneration", 1)
        ),
        "subject": {
            "node": node,
            "service": service,
        },
        "generation": generation,
        "state": "burned",
        "burned": {
            "fingerprint": fingerprint,
            "reason": reason,
            "burnedAt": now_utc(),
            "scope": "subject-generation",
        },
        "createdAt": now_utc(),
    }
    return prepare_event(
        registry_path,
        event,
        policy,
        leader_public_key,
        signing_key,
        None,
    )


def append_stale_burn_events(
    *,
    registry_path: Path,
    policy: dict,
    leader: str,
    leader_key_arg: str | None,
    signing_key: Path | None,
    targets: list[tuple[dict, str]],
) -> list[Path]:
    appended = []
    for old_event, reason in targets:
        subject = old_event.get("subject") or {}
        node = subject.get("node")
        service = subject.get("service")
        generation = identity_generation(old_event)
        if not isinstance(node, str) or not isinstance(service, str):
            continue
        if generation is None:
            continue
        fingerprint = registry.public_identity_fingerprint(
            service, old_event.get("public") or {}
        )
        if not fingerprint:
            continue
        appended.append(
            append_burn_event(
                registry_path=registry_path,
                policy=policy,
                leader=leader,
                leader_key_arg=leader_key_arg,
                node=node,
                service=service,
                generation=generation,
                fingerprint=fingerprint,
                reason=reason,
                signing_key=signing_key,
            )
        )
    return appended


def build_live_identity_matrices(
    hosts: list[str],
    live_records: dict[str, dict[str, list[dict]]],
    services: set[str] | None = None,
    status_records: dict[str, dict] | None = None,
    burn_limit: int | None = DEFAULT_MATRIX_BURN_LIMIT,
) -> list[dict]:
    by_leader: dict[str, dict[str, dict[str, list[dict]]]] = {}
    host_set = set(hosts)
    for node, service_records in live_records.items():
        if node not in host_set:
            continue
        for service_name, records in service_records.items():
            if services and service_name not in services:
                continue
            for record in records:
                leader = record.get("leader") or "unknown"
                by_leader.setdefault(leader, {}).setdefault(service_name, {}).setdefault(
                    node, []
                ).append(record)

    matrices = []
    for leader, leader_services in sorted(by_leader.items()):
        rows = []
        for service_name in sorted(leader_services, key=service_sort_key):
            service_nodes = {
                node: records_with_burn_limit(
                    annotate_identity_records_status(
                        records_after_generation_burns(records),
                        node=node,
                        service=service_name,
                        status_records=status_records,
                    ),
                    burn_limit,
                )
                for node, records in leader_services[service_name].items()
            }
            rows.append(
                {
                    "service": service_name,
                    "nodes": {
                        node: {
                            "cell": live_identity_cell(service_nodes.get(node, []))
                            or "-",
                            "records": service_nodes.get(node, []),
                        }
                        for node in hosts
                    },
                }
            )
        matrices.append(
            {
                "leader": leader,
                "services": [row["service"] for row in rows],
                "rows": rows,
            }
        )
    return matrices


def live_identity_matrices_from_registry(
    registry_path: Path,
    hosts: list[str],
    services: set[str] | None = None,
    status_records: dict[str, dict] | None = None,
    burn_limit: int | None = DEFAULT_MATRIX_BURN_LIMIT,
) -> list[dict]:
    if not registry_path.exists():
        return []
    by_leader: dict[str, dict[str, dict[str, list[dict]]]] = {}
    host_set = set(hosts)
    for _path, event in registry.identity_events(registry.load_events(registry_path)):
        subject = event.get("subject") or {}
        node = subject.get("node")
        service_name = subject.get("service")
        leader = event.get("leader")
        if not isinstance(node, str) or node not in host_set:
            continue
        if not isinstance(service_name, str):
            continue
        if services and service_name not in services:
            continue
        if not isinstance(leader, str) or not leader:
            leader = "unknown"
        record = {
            "generation": event.get("generation"),
            "state": event.get("state"),
            "leader": leader,
            "eventId": event.get("eventId"),
            "eventHash": event.get("eventHash"),
            "public": event.get("public", {}),
            "privateDelivery": event.get("privateDelivery"),
            "localUsable": event.get("localUsable", True),
            "createdAt": event.get("createdAt"),
            "payloadHash": event.get("payloadHash"),
        }
        by_leader.setdefault(leader, {}).setdefault(service_name, {}).setdefault(
            node, []
        ).append(record)

    live_records: dict[str, dict[str, list[dict]]] = {}
    matrices = []
    for leader, leader_services in sorted(by_leader.items()):
        live_records.clear()
        for service_name, service_nodes in leader_services.items():
            for node, records in service_nodes.items():
                live_records.setdefault(node, {})[service_name] = records
        matrices.extend(
            build_live_identity_matrices(
                hosts, live_records, services, status_records, burn_limit
            )
        )
    return matrices


def fetch_live_identity_records(
    policy_path: Path, out: Path
) -> dict[str, dict[str, list[dict]]]:
    policy = load_policy(policy_path)
    try:
        follower.fetch_and_materialize(policy, out)
    except Exception as error:
        print(f"Warning: live identity fetch failed: {error}", file=sys.stderr)
    return live_identity_records(out)


def fetch_status_acknowledgements(
    policy: dict,
    hosts: list[str],
    cache_dir: Path,
) -> tuple[dict[str, dict], dict[str, str]]:
    status_records = {}
    failures = {}
    publishers = policy.get("statusPublishers") or {}
    for node in hosts:
        if node not in publishers:
            continue
        try:
            status_records[node] = status.fetch_status_record(policy, node, cache_dir)
        except Exception as error:
            failures[node] = str(error)
    return status_records, failures


def ssh_target_prefix(node: str, bootstrap_entry: dict) -> list[str]:
    # The "-bootstrap" alias is what the operator's ssh config keys its
    # `Match originalhost` identity-file injection on; the raw targetHost
    # IP never matches it and falls back to no identity at all.
    target_host = f"{node}-bootstrap" if bootstrap_entry.get("targetHost") else node
    ssh_user = bootstrap_entry.get("sshUser") or "root"
    command = ["ssh"]
    identity_file = bootstrap_entry.get("identityFile")
    if identity_file:
        command.extend(["-i", identity_file])
    command.append(f"{ssh_user}@{target_host}")
    return command


def render_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render_row(row: list[str]) -> str:
        return "  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row))

    divider = "  ".join("-" * width for width in widths)
    return "\n".join([render_row(headers), divider, *[render_row(row) for row in rows]])


def source_ledger_for_service(service: str) -> str:
    if service == "host-age":
        return "inventory/keys/host-age-recipients.nix"
    return IDENTITY_SOURCE_FILES.get(
        service, "inventory/identity-services/identities.nix"
    )


def flake_root(flake: str) -> Path:
    return Path(flake).expanduser().resolve()


def nix_file_json(path: Path) -> dict:
    completed = subprocess.run(
        ["nix", "eval", "--json", "--file", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return json.loads(completed.stdout)


def render_nix(value, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(value, dict):
        if not value:
            return "{ }"
        lines = ["{"]
        for key in sorted(value.keys()):
            rendered = render_nix(value[key], indent + 2)
            lines.append(f"{space}  {json.dumps(str(key))} = {rendered};")
        lines.append(f"{space}}}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return "[ ]"
        rendered_items = " ".join(render_nix(item, indent + 2) for item in value)
        return f"[ {rendered_items} ]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value))


def write_nix_value(path: Path, value) -> None:
    path.write_text(f"{render_nix(value)}\n", encoding="utf-8")


def identity_source_path(flake: str, service: str) -> Path:
    relative = IDENTITY_SOURCE_FILES.get(service)
    if not relative:
        raise ValueError(
            f"no writable source ledger is configured for service {service!r}"
        )
    return flake_root(flake) / relative


def ssh_completed(
    node: str, flake: str, remote_command: str, *, input_text: str | None = None
) -> subprocess.CompletedProcess:
    bootstrap_entry = transport.host_bootstrap(flake).get(node, {})
    command = ssh_target_prefix(node, bootstrap_entry)
    command.extend(["bash", "-s", "--"])
    return subprocess.run(
        command,
        input=input_text or remote_command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def capture_host_age_public(
    node: str, flake: str, target_path: str = DEFAULT_HOST_AGE_TARGET_PATH
) -> str:
    target_host, ssh_user = resolve_target(node, flake)
    completed = subprocess.run(
        [
            "ssh",
            f"{ssh_user}@{target_host}",
            f"sed -n 's/^# public key: //p' {target_path}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return completed.stdout.strip()


def ensure_host_age_key(
    node: str, flake: str, target_path: str = DEFAULT_HOST_AGE_TARGET_PATH
) -> str:
    target_host, ssh_user = resolve_target(node, flake)
    generate = (
        f"(command -v age-keygen >/dev/null 2>&1 && age-keygen -o {target_path} "
        f"|| nix shell nixpkgs#age -c age-keygen -o {target_path})"
    )
    command = (
        "install -d -m 0700 /var/lib/cluster-identity/age "
        f"&& test -s {target_path} || {generate} "
        f"&& chmod 0400 {target_path}"
    )
    subprocess.run(["ssh", f"{ssh_user}@{target_host}", command], check=True)
    return capture_host_age_public(node, flake, target_path)


def rotate_host_age_key(
    node: str, flake: str, target_path: str = DEFAULT_HOST_AGE_TARGET_PATH
) -> tuple[str, str]:
    target_host, ssh_user = resolve_target(node, flake)
    backup = f"{target_path}.old-{now_utc().replace(':', '').replace('-', '')}"
    generate = (
        f"(command -v age-keygen >/dev/null 2>&1 && age-keygen -o {target_path} "
        f"|| nix shell nixpkgs#age -c age-keygen -o {target_path})"
    )
    command = (
        "install -d -m 0700 /var/lib/cluster-identity/age "
        f"&& if [ -s {target_path} ]; then mv {target_path} {backup}; fi "
        f"&& {generate} "
        f"&& chmod 0400 {target_path}"
    )
    subprocess.run(["ssh", f"{ssh_user}@{target_host}", command], check=True)
    return capture_host_age_public(node, flake, target_path), backup


def capture_yggdrasil_public(node: str, flake: str) -> dict:
    completed = ssh_completed(node, flake, "", input_text=YGGDRASIL_DISCOVERY_SCRIPT)
    return json.loads(completed.stdout)


def capture_ssh_host_key(node: str, flake: str) -> str:
    completed = ssh_completed(node, flake, "cat /etc/ssh/ssh_host_ed25519_key.pub")
    return completed.stdout.strip()


def capture_radicle_node_id(node: str, flake: str) -> str:
    completed = ssh_completed(
        node,
        flake,
        "sudo -u radicle env RAD_HOME=/var/lib/radicle sh -lc \"rad self --did | sed 's/^did:key://'\"",
    )
    return completed.stdout.strip()


def status_ipns_script(key_name: str) -> str:
    return f"""
set -euo pipefail
key_name={shlex.quote(key_name)}
api=/unix/run/ipfs.sock
current="$(ipfs --api="$api" key ls -l | awk -v key="$key_name" '$2 == key {{ print $1 }}')"
if [ -n "$current" ]; then
  printf '%s\n' "$current"
else
  ipfs --api="$api" key gen --type=ed25519 "$key_name"
fi
"""


def is_local_node(node: str) -> bool:
    local_names = {socket.gethostname(), socket.getfqdn()}
    return node in local_names


def capture_status_ipns_name(node: str, flake: str) -> str:
    key_name = status.default_status_key_name(node)
    script = status_ipns_script(key_name)
    if is_local_node(node):
        completed = subprocess.run(
            ["bash", "-s", "--"],
            input=script,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    else:
        completed = ssh_completed(node, flake, "", input_text=script)
    return completed.stdout.strip().splitlines()[-1]


def capture_onion_mirror_identity(node: str, flake: str) -> dict:
    script = """
set -euo pipefail
service_dir=/var/lib/tor/onion/cluster-identity
public_key="$(sudo base64 -w0 "$service_dir/hs_ed25519_public_key")"
hostname="$(sudo cat "$service_dir/hostname")"
printf '{"publicKeyFileBase64":"%s","hostname":"%s"}\\n' "$public_key" "$hostname"
"""
    completed = ssh_completed(node, flake, "", input_text=script)
    payload = json.loads(completed.stdout)
    onion_address = onion.derive_onion_address_from_public_key_file(
        payload["publicKeyFileBase64"]
    )
    if payload["hostname"] != onion_address:
        raise ValueError(
            f"Tor onion hostname {payload['hostname']!r} does not match "
            "the enrolled public key"
        )
    return {
        "publicKeyFileBase64": payload["publicKeyFileBase64"],
        "onionAddress": onion_address,
    }


def host_age_recipients_path(flake: str) -> Path:
    return flake_root(flake) / "inventory/keys/host-age-recipients.nix"


def update_host_age_recipient_file(
    flake: str, node: str, public_key: str, generation: int = 1
) -> None:
    path = host_age_recipients_path(flake)
    recipients = nix_file_json(path)
    recipients[node] = {
        "generation": generation,
        "publicKey": public_key,
        "keyType": "age-x25519",
        "privateKeyPath": DEFAULT_HOST_AGE_TARGET_PATH,
        "enrolledAt": now_utc(),
        "enrollment": "root-ssh",
    }
    write_nix_value(path, recipients)


def update_identity_source_file(
    flake: str, service: str, node: str, record: dict
) -> None:
    path = identity_source_path(flake, service)
    records = nix_file_json(path)
    records[node] = record
    write_nix_value(path, records)


def generate_ipns_key() -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="cluster-identity-ipns-") as temporary:
        ipfs_path = Path(temporary) / "ipfs"
        env = os.environ.copy()
        env["IPFS_PATH"] = str(ipfs_path)
        subprocess.run(
            ["ipfs", "init", "--profile=server"],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
        )
        key_name = "pending-cluster-identity-enrollment"
        completed = subprocess.run(
            ["ipfs", "key", "gen", "--type=ed25519", key_name],
            check=True,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
        )
        ipns_name = completed.stdout.strip()
        exported_path = Path(temporary) / "ipns-private.pem"
        subprocess.run(
            [
                "ipfs",
                "key",
                "export",
                "--format=pem-pkcs8-cleartext",
                f"--output={exported_path}",
                key_name,
            ],
            check=True,
            env=env,
        )
        exported_path.chmod(0o600)
        return ipns_name, exported_path.read_text(encoding="utf-8")


def generate_ssh_key(comment: str) -> tuple[str, str]:
    with tempfile.TemporaryDirectory(prefix="cluster-identity-ssh-") as temporary:
        key_path = Path(temporary) / "id_ed25519"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                comment,
                "-f",
                str(key_path),
            ],
            check=True,
        )
        return (
            key_path.with_suffix(".pub").read_text(encoding="utf-8").strip(),
            key_path.read_text(encoding="utf-8"),
        )


def leader_user_for_host(inventory: dict, node: str) -> tuple[str, str]:
    host = (inventory.get("hosts") or {}).get(node) or {}
    users = inventory.get("users") or {}
    leader_users = [
        user_name
        for user_name in host.get("users") or []
        if (
            ((users.get(user_name) or {}).get("org") or {}).get("clusterIdentity") or {}
        ).get("role")
        == "leader"
    ]
    if len(leader_users) != 1:
        raise ValueError(
            f'{node!r} must have exactly one user with org.clusterIdentity.role = "leader"'
        )
    user_name = leader_users[0]
    home = ((users.get(user_name) or {}).get("home") or {}).get("directory")
    if not home:
        raise ValueError(f"leader user {user_name!r} has no home.directory")
    return user_name, f"{home}/.ssh/cluster-leader-ed25519"


def sudo_command(command: list[str], age_key_file: Path) -> list[str]:
    privilege = (
        Privilege.USER
        if os.geteuid() == 0 or os.access(age_key_file, os.R_OK)
        else Privilege.ROOT_LOCAL
    )
    return privileged_command(
        ["env", f"SOPS_AGE_KEY_FILE={age_key_file}", *command],
        privilege,
    )


def update_sops_string_map(
    path: Path,
    key: str,
    value: str,
    age_key_file: Path,
    *,
    flake: str,
) -> None:
    sops = shutil.which("sops")
    if not sops:
        raise RuntimeError("sops is required to update the encrypted identity ledger")

    values: dict[str, str] = {}
    if path.exists():
        decrypted = subprocess.run(
            sudo_command(
                [sops, "--decrypt", "--output-type", "json", str(path)], age_key_file
            ),
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        values = json.loads(decrypted.stdout)
    values[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=".leader-ipns-keys.",
        suffix=".json",
        dir=path.parent,
        delete=False,
    ) as plaintext:
        json.dump(values, plaintext)
        plaintext.write("\n")
        plaintext_path = Path(plaintext.name)
    plaintext_path.chmod(0o600)

    try:
        root = flake_root(flake)
        filename_override = str(path.relative_to(root))
        encrypted = subprocess.run(
            sudo_command(
                [
                    sops,
                    "--encrypt",
                    "--input-type",
                    "json",
                    "--output-type",
                    "yaml",
                    "--filename-override",
                    filename_override,
                    str(plaintext_path),
                ],
                age_key_file,
            ),
            check=True,
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
        )
        path.write_text(encrypted.stdout, encoding="utf-8")
    finally:
        plaintext_path.unlink(missing_ok=True)


def stage_flake_paths(flake: str, paths: list[Path]) -> None:
    root = flake_root(flake)
    relative_paths = [str(path.relative_to(root)) for path in paths]
    subprocess.run(["git", "-C", str(root), "add", "--", *relative_paths], check=True)


def generated_identity_record(service: str, node: str, payload: dict) -> dict:
    if service == "yggdrasil":
        address = payload["address"]
        return {
            "generation": 1,
            "state": "active",
            "sourceTimestamp": now_utc(),
            "public": {
                "yggdrasilAddress": address,
                "yggdrasilPublicKey": payload["publicKey"],
                "deployHost": address,
            },
            "private": {
                "status": "not-yet-imported-to-encrypted-ledger",
                "recipientHost": node,
                "targetPath": "/var/lib/yggdrasil/private.key",
            },
        }
    if service == "ssh-host":
        return {
            "generation": 1,
            "state": "active",
            "sourceTimestamp": now_utc(),
            "public": {
                "sshHostKey": payload["sshHostKey"],
            },
        }
    if service == "radicle":
        return {
            "generation": 1,
            "state": "active",
            "sourceTimestamp": now_utc(),
            "public": {
                "radicleNodeId": payload["radicleNodeId"],
            },
        }
    if service == "git-annex":
        public = {
            "gitAnnexEndpoint": payload["gitAnnexEndpoint"],
            "repoRoot": payload["repoRoot"],
            "hostAlias": payload["hostAlias"],
        }
        ssh_public_key = payload.get("sshPublicKey")
        if ssh_public_key:
            public["sshPublicKey"] = ssh_public_key
        group = payload.get("group")
        if group:
            public["group"] = group
        return {
            "generation": 1,
            "state": "active",
            "sourceTimestamp": now_utc(),
            "public": public,
        }
    if service == "ipns-publisher":
        return {
            "generation": 1,
            "state": "active",
            "sourceTimestamp": now_utc(),
            "public": {
                "ipnsName": payload["ipnsName"],
            },
            "private": {
                "sopsPath": "inventory/keys/leaders/leader-ipns-keys.sops.yaml",
                "sopsKey": node,
            },
        }
    if service == "onion-mirror":
        return {
            "generation": 1,
            "state": "active",
            "sourceTimestamp": now_utc(),
            "public": {
                "keyType": "tor-v3-ed25519",
                "publicKeyFileBase64": payload["publicKeyFileBase64"],
                "onionAddress": payload["onionAddress"],
                "onionUrl": f"http://{payload['onionAddress']}",
            },
        }
    if service == "status-ipns":
        key_name = payload.get("keyName") or status.default_status_key_name(node)
        record = {
            "generation": 1,
            "state": "active",
            "sourceTimestamp": now_utc(),
            "public": {
                "ipnsName": payload["ipnsName"],
                "keyName": key_name,
            },
        }
        if payload.get("sopsPath") and payload.get("sopsKey"):
            record["private"] = {
                "custody": "leader-generated-sops",
                "sopsPath": payload["sopsPath"],
                "sopsKey": payload["sopsKey"],
                "keyName": key_name,
            }
        return record
    if service == "leader-user-ssh":
        return {
            "generation": 1,
            "state": "active",
            "sourceTimestamp": now_utc(),
            "public": {
                "sshPublicKey": payload["sshPublicKey"],
                "user": payload["user"],
            },
            "private": {
                "sopsPath": "inventory/keys/identities/cluster-private-identities.sops.yaml",
                "sopsKey": f"{node}-leader-user-ssh",
                "targetPath": payload["targetPath"],
            },
        }
    raise ValueError(f"automatic generation is not implemented for service {service!r}")


def derive_git_annex_payload(inventory: dict, node: str) -> dict:
    ygg_node = (
        ((inventory.get("networks") or {}).get("privateYggdrasil") or {}).get("nodes")
        or {}
    ).get(node) or {}
    aliases = ygg_node.get("aliases") or []
    host_alias = aliases[0] if aliases else f"{node}-ygg"
    repo_root = (
        (((inventory.get("storageFabric") or {}).get("annex")) or {}).get("repoRoot")
    ) or "/srv/annex/cluster-data"
    host = (inventory.get("hosts") or {}).get(node) or {}
    group = ((((host.get("org") or {}).get("storage")) or {}).get("annex") or {}).get(
        "group"
    )
    ssh_public_key = (
        (((host.get("org") or {}).get("storage")) or {}).get("annex") or {}
    ).get("sshPublicKey")
    return {
        "gitAnnexEndpoint": f"annex+ssh://{host_alias}{repo_root}",
        "hostAlias": host_alias,
        "repoRoot": repo_root,
        "group": group,
        "sshPublicKey": ssh_public_key,
    }


def ensure_registry_git_repo(registry_path: Path) -> None:
    if not (registry_path / ".git").exists():
        registry.init_registry(registry_path)


def path_is_accessible(path: Path, mode: int) -> bool:
    try:
        if path.exists():
            return os.access(path, mode)
    except PermissionError:
        return False

    parent = path.parent
    while True:
        try:
            if parent.exists():
                return os.access(parent, os.W_OK | os.X_OK)
        except PermissionError:
            return False
        if parent == parent.parent:
            return False
        parent = parent.parent


def identity_publish_requires_sudo(args) -> bool:
    if os.geteuid() == 0 or os.environ.get("CLUSTERCTL_NO_SUDO") == "1":
        return False
    if not path_is_accessible(args.registry, os.R_OK | os.W_OK | os.X_OK):
        return True
    if not args.no_reconcile and not path_is_accessible(
        args.out,
        os.R_OK | os.W_OK | os.X_OK,
    ):
        return True
    if args.signature:
        return False
    try:
        key_path = signing_key_path(load_policy(args.policy), args.signing_key)
    except ValueError:
        return False
    return not path_is_accessible(key_path, os.R_OK)


def clusterctl_executable() -> str:
    executable = os.environ.get("CLUSTERCTL_EXECUTABLE") or shutil.which("clusterctl")
    if not executable:
        raise RuntimeError(
            "cannot find the clusterctl executable for privileged publication"
        )
    return executable


def identity_publish_command(args) -> list[str]:
    command = [
        clusterctl_executable(),
        "--flake",
        args.flake,
        "identity",
        "publish",
        "--registry",
        str(args.registry),
        "--out",
        str(args.out),
        "--policy",
        str(args.policy),
    ]
    for service in args.service:
        command.extend(["--service", service])
    for node in args.node:
        command.extend(["--node", node])
    if args.generation is not None:
        command.extend(["--generation", str(args.generation)])
    if args.state:
        command.extend(["--state", args.state])
    if args.leader:
        command.extend(["--leader", args.leader])
    if args.leader_key:
        command.extend(["--leader-key", args.leader_key])
    if args.signature:
        command.extend(["--signature", args.signature])
    if args.signing_key:
        command.extend(["--signing-key", str(args.signing_key)])
    if args.allow_duplicate:
        command.append("--allow-duplicate")
    if getattr(args, "allow_cross_leader_publish", False):
        command.append("--allow-cross-leader-publish")
    command.append(
        "--burn-stale"
        if getattr(args, "burn_stale", True)
        else "--no-burn-stale"
    )
    if getattr(args, "burn_guarded_stale", False):
        command.append("--burn-guarded-stale")
    if args.no_commit:
        command.append("--no-commit")
    if args.no_reconcile:
        command.append("--no-reconcile")
    command.append("--fetch" if args.fetch else "--no-fetch")
    command.append("--push" if args.push else "--no-push")
    for remote in args.remote:
        command.extend(["--remote", remote])
    if args.notify:
        command.append("--notify")
    return command


def publish_generated_identities(args) -> int:
    if not identity_publish_requires_sudo(args):
        return cmd_identity_publish(args)

    print(
        "Publishing generated identities with sudo for privileged registry access.",
        flush=True,
    )
    return run_command(
        identity_publish_command(args),
        privilege=Privilege.ROOT_LOCAL,
        runner=subprocess.run,
        authorization_runner=subprocess.run,
    ).returncode


def build_identity_matrix(
    inventory: dict,
    services: set[str] | None = None,
    nodes: set[str] | None = None,
    live_records: dict[str, dict[str, list[dict]]] | None = None,
    live_matrices: list[dict] | None = None,
    status_records: dict[str, dict] | None = None,
    burn_limit: int | None = DEFAULT_MATRIX_BURN_LIMIT,
) -> dict:
    hosts = inventory_hosts(inventory, nodes)
    identities = ((inventory.get("identities") or {}).get("services")) or {}
    live_records = live_records or {}
    requirements_by_node = {
        node: identity_requirements_for_host(inventory, node) for node, _host in hosts
    }
    desired_by_node = {
        node: set(requirements.keys())
        for node, requirements in requirements_by_node.items()
    }

    service_names = set()
    for desired in desired_by_node.values():
        service_names.update(desired)
    for service_name, service_records in identities.items():
        for node in service_records.keys():
            if nodes and node not in nodes:
                continue
            service_names.add(service_name)
    for node, service_records in live_records.items():
        if nodes and node not in nodes:
            continue
        service_names.update(service_records.keys())

    if services:
        service_names &= services

    ordered_services = sorted(service_names, key=service_sort_key)
    matrix_rows: list[dict] = []
    missing: list[dict] = []
    extra: list[dict] = []

    for service_name in ordered_services:
        row_cells: dict[str, dict] = {}
        service_records = identities.get(service_name) or {}
        for node, _host in hosts:
            desired = service_name in desired_by_node.get(node, set())
            record = service_records.get(node)
            annotated_record = annotate_identity_record_status(
                record, node=node, service=service_name, status_records=status_records
            )
            live_service_records = records_with_burn_limit(
                annotate_identity_records_status(
                    records_after_generation_burns(
                        live_records.get(node, {}).get(service_name, [])
                    ),
                    node=node,
                    service=service_name,
                    status_records=status_records,
                ),
                burn_limit,
            )
            if desired and record:
                cell = identity_record_cell(annotated_record or record)
                status = "present"
            elif desired:
                cell = "missing"
                status = "missing"
                missing.append(
                    {
                        "node": node,
                        "service": service_name,
                        "desired": True,
                        "suggestedGeneration": 1,
                        "sourceLedger": (
                            requirements_by_node.get(node, {})
                            .get(service_name, {})
                            .get("sourceLedger")
                            or source_ledger_for_service(service_name)
                        ),
                        "requirement": requirements_by_node.get(node, {}).get(
                            service_name, {}
                        ),
                    }
                )
            elif record:
                cell = f"extra {identity_record_cell(annotated_record or record)}"
                status = "extra"
                extra.append(
                    {
                        "node": node,
                        "service": service_name,
                        "desired": False,
                        "sourceLedger": source_ledger_for_service(service_name),
                    }
                )
            else:
                cell = "-"
                status = "not-applicable"

            row_cells[node] = {
                "cell": cell,
                "status": status,
                "desired": desired,
                "record": annotated_record,
                "liveRecord": live_service_records,
            }

        matrix_rows.append(
            {
                "service": service_name,
                "nodes": row_cells,
            }
        )

    return {
        "hosts": [node for node, _host in hosts],
        "services": ordered_services,
        "rows": matrix_rows,
        "liveMatrices": live_matrices
        if live_matrices is not None
        else build_live_identity_matrices(
            [node for node, _host in hosts],
            live_records,
            services,
            status_records,
            burn_limit,
        ),
        "missing": missing,
        "extra": extra,
        "legend": {
            "-": "not desired on this host",
            "missing": "desired by inventory metadata but absent from the flake identity source ledger",
            "gN/x": "present in the flake identity source ledger at generation N, state x",
            "extra gN/x": "present in the flake identity source ledger but no longer implied by current inventory metadata",
            "live matrix": "accepted live registry events grouped by publishing leader",
        },
    }


def next_record_generation(record: dict | None) -> int:
    if not record:
        return 1
    generation = record.get("generation")
    if isinstance(generation, int):
        return generation + 1
    return 1


def process_error_message(error: subprocess.CalledProcessError) -> str:
    details = (error.stderr or error.stdout or "").strip()
    if details:
        return f"{error.cmd!r} exited {error.returncode}: {details}"
    return f"{error.cmd!r} exited {error.returncode}"


def identity_guidance(
    node: str, service: str, record: dict | None, bootstrap_entry: dict
) -> list[str]:
    commands: list[str] = []
    publish_command = f"clusterctl identity publish --node {shlex.quote(node)} --service {shlex.quote(service)}"
    generate_command = f"clusterctl identity generate-missing --node {shlex.quote(node)} --service {shlex.quote(service)}"
    ssh_prefix = shlex.join(ssh_target_prefix(node, bootstrap_entry))
    generation = next_record_generation(record)

    if service == "host-age":
        if record:
            commands.append(
                f"clusterctl identity rotate {shlex.quote(node)} host-age"
            )
        else:
            commands.append(generate_command)
        return commands

    if service == "ipns-publisher":
        if record is None:
            commands.append(generate_command)
        commands.append(
            "# rebuild the leader so its SOPS-backed IPNS publisher unit is enabled"
        )
        commands.append(f"nix run .#deploy-rs -- .#{shlex.quote(node)}")
        return commands

    if service == "status-ipns":
        if record is None:
            commands.append(generate_command)
        commands.append(
            "# deploy the node so its status publisher timer has the enrolled IPNS name"
        )
        commands.append(f"clusterctl deploy {shlex.quote(node)}")
        commands.append(
            f"systemctl start cluster-identity-status-publish.service # on {node}"
        )
        return commands

    if service == "leader-user-ssh":
        if record is None:
            commands.append(generate_command)
        commands.append(
            "# deploy every host so the new public key is trusted fleet-wide"
        )
        commands.append("clusterctl deploy all")
        return commands

    if service == "yggdrasil":
        if record is None:
            commands.append(generate_command)
        bootstrap_parts = [
            "nix",
            "run",
            ".#yggdrasil-bootstrap",
            "--",
            "--host",
            node,
        ]
        target_host = bootstrap_entry.get("targetHost")
        identity_file = bootstrap_entry.get("identityFile")
        ssh_user = bootstrap_entry.get("sshUser")
        if target_host:
            bootstrap_parts.extend(["--target", target_host])
        if ssh_user:
            bootstrap_parts.extend(["--ssh-user", ssh_user])
        if identity_file:
            bootstrap_parts.extend(["--identity-file", identity_file])
        commands.append(shlex.join(bootstrap_parts))
        commands.append(
            "# if you rotated the host key first, bump generation and update inventory/identity-services/yggdrasil.nix"
        )
        commands.append(publish_command)
        if record and (record.get("private") or {}).get("targetPath"):
            target_path = (record.get("private") or {}).get("targetPath")
            commands.append(
                f"clusterctl bundle seal {shlex.quote(node)} yggdrasil --generation {generation} --source ./private/{node}-yggdrasil.key --target-path {shlex.quote(target_path)} --from-inventory"
            )
            commands.append(
                f"clusterctl receipt collect {shlex.quote(node)} yggdrasil --generation {generation}"
            )
            commands.append(
                f"clusterctl identity promote {shlex.quote(node)} yggdrasil --generation {generation}"
            )
        return commands

    if service == "ssh-host":
        if record is None:
            commands.append(generate_command)
        commands.append(f"{ssh_prefix} 'cat /etc/ssh/ssh_host_ed25519_key.pub'")
        commands.append(
            "# update inventory/identity-services/ssh-host.nix with the current public host key"
        )
        commands.append(publish_command)
        return commands

    if service == "radicle":
        if record is None:
            commands.append(generate_command)
        commands.append(
            f'{ssh_prefix} "sudo -u radicle env RAD_HOME=/var/lib/radicle sh -lc \\"rad self --did | sed \'s/^did:key://\'\\""'
        )
        commands.append(
            "# update inventory/identity-services/radicle.nix with the current public node id"
        )
        commands.append(publish_command)
        return commands

    if service == "git-annex":
        if record is None:
            commands.append(generate_command)
        commands.append(
            "# record the host's git-annex endpoint metadata in inventory/identity-services/git-annex.nix"
        )
        commands.append(publish_command)
        return commands

    commands.append(publish_command)
    return commands


def cmd_identity_matrix(args) -> int:
    inventory = transport.inventory(args.flake)
    services = normalize_filter_values(args.service)
    nodes = normalize_filter_values(args.node)
    matrix_hosts = [node for node, _host in inventory_hosts(inventory, nodes)]
    live_matrices = None
    status_records = None
    status_failures = {}
    policy = None
    burn_limit = getattr(args, "burn_limit", None)
    if burn_limit is None:
        burn_limit = DEFAULT_MATRIX_BURN_LIMIT
    status_ack_enabled = getattr(args, "status_ack", True)
    status_cache = getattr(args, "status_cache", DEFAULT_STATUS_CACHE)
    if args.no_live:
        live_records = {}
    elif args.fetch:
        live_records = fetch_live_identity_records(args.policy, args.out)
    else:
        live_records = live_identity_records(args.out)
    if not args.no_live:
        try:
            policy = load_policy(args.policy)
            if status_ack_enabled:
                status_records, status_failures = fetch_status_acknowledgements(
                    policy, matrix_hosts, status_cache
                )
            live_matrices = live_identity_matrices_from_registry(
                follower.accepted_registry_path(policy),
                matrix_hosts,
                services,
                status_records,
                burn_limit,
            )
        except Exception as error:
            print(
                f"Warning: accepted live registry read failed: {error}",
                file=sys.stderr,
            )
            live_matrices = []
        if not live_matrices:
            live_matrices = build_live_identity_matrices(
                matrix_hosts, live_records, services, status_records, burn_limit
            )
    report = build_identity_matrix(
        inventory,
        services,
        nodes,
        live_records,
        live_matrices,
        status_records,
        burn_limit,
    )
    report["statusAcknowledgements"] = {
        "enabled": bool(status_ack_enabled),
        "reachable": sorted((status_records or {}).keys()),
        "failures": status_failures,
    }
    report["matrixSettings"] = {"burnLimit": burn_limit}

    if args.only_missing:
        filtered_rows = []
        filtered_services = []
        for row in report["rows"]:
            if any(cell["status"] == "missing" for cell in row["nodes"].values()):
                filtered_rows.append(row)
                filtered_services.append(row["service"])
        report["rows"] = filtered_rows
        report["services"] = filtered_services

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    headers = ["service", *report["hosts"]]
    rows = []
    for row in report["rows"]:
        rows.append(
            [row["service"], *[row["nodes"][node]["cell"] for node in report["hosts"]]]
        )

    print("Desired identity matrix (services x hosts)")
    if rows:
        print(render_table(headers, rows))
    else:
        print("No identity rows matched the current filters.")

    for matrix in report["liveMatrices"]:
        live_rows = []
        for row in matrix["rows"]:
            live_rows.append(
                [
                    row["service"],
                    *[row["nodes"][node]["cell"] for node in report["hosts"]],
                ]
            )
        print(f"\nLive identity matrix for leader {matrix['leader']}")
        if live_rows:
            print(render_table(headers, live_rows))
        else:
            print("No live identity rows matched the current filters.")

    print("\nLegend:")
    print("  -: not desired on this host")
    print(
        "  missing: desired by inventory metadata but absent from the flake identity source ledger"
    )
    print(
        "  gN/x: present with generation N and state x (a=active, s=staged, d=deprecated, b=burned)"
    )
    print(
        "  extra gN/x: present in the ledger but not implied by current inventory metadata"
    )
    print("  live matrices: accepted registry events grouped by publishing leader")
    print(
        "  au: ledger-active but not confirmed by the target's signed status IPNS record"
    )
    print(
        "  aa: target status is active and every reachable peer status agrees"
    )
    if report["statusAcknowledgements"]["enabled"]:
        reachable = report["statusAcknowledgements"]["reachable"]
        failures = report["statusAcknowledgements"]["failures"]
        print(
            "  status ack: "
            f"{len(reachable)} reachable"
            + (f", {len(failures)} failed" if failures else "")
        )

    missing = report["missing"]
    extra = report["extra"]

    if missing:
        print("\nMissing desired identities:")
        for item in missing:
            if args.only_missing or item["service"] in report["services"]:
                print(f"  - {item['node']}/{item['service']} -> {item['sourceLedger']}")
    else:
        print("\nMissing desired identities: none")

    if extra:
        print("\nExtra ledger identities to review:")
        for item in extra:
            if item["service"] in report["services"]:
                print(f"  - {item['node']}/{item['service']} -> {item['sourceLedger']}")

    bootstrap = transport.host_bootstrap(args.flake)
    guidance_targets: list[tuple[str, str, dict | None]] = []

    for row in report["rows"]:
        service_name = row["service"]
        for node in report["hosts"]:
            cell = row["nodes"][node]
            if args.only_missing:
                selected = cell["status"] == "missing"
            elif args.node or args.service:
                selected = cell["status"] in {"missing", "present"}
            else:
                selected = cell["status"] == "missing"
            if selected:
                guidance_targets.append((node, service_name, cell["record"]))

    if guidance_targets:
        print("\nCommand guide:")
        seen: set[tuple[str, str]] = set()
        for node, service_name, record in guidance_targets:
            if (node, service_name) in seen:
                continue
            seen.add((node, service_name))
            print(f"\n[{node} / {service_name}]")
            for command in identity_guidance(
                node, service_name, record, bootstrap.get(node) or {}
            ):
                print(command)

    return 0


def current_identity_record(inventory: dict, node: str, service: str) -> dict | None:
    services = ((inventory.get("identities") or {}).get("services")) or {}
    return (services.get(service) or {}).get(node)


def desired_identity_requirement(inventory: dict, node: str, service: str) -> dict | None:
    if node not in ((inventory.get("hosts") or {}).keys()):
        return None
    return identity_requirements_for_host(inventory, node).get(service)


def cmd_identity_rotate(args) -> int:
    inventory = transport.inventory(args.flake)
    requirement = desired_identity_requirement(inventory, args.node, args.service)
    if requirement is None:
        print(
            f"{args.node}/{args.service} is not desired by current inventory metadata.",
            file=sys.stderr,
        )
        return 2

    current = current_identity_record(inventory, args.node, args.service)
    if current is None and not args.allow_missing:
        print(
            f"{args.node}/{args.service} has no current source-ledger record; "
            "use identity generate-missing or pass --allow-missing.",
            file=sys.stderr,
        )
        return 2

    known_generation = known_identity_generation(
        current,
        args.registry,
        args.policy,
        args.out,
        args.node,
        args.service,
    )
    if args.generation is not None and args.generation <= known_generation:
        print(
            f"{args.node}/{args.service} has known generation "
            f"{known_generation}; choose a higher --generation.",
            file=sys.stderr,
        )
        return 2
    generation = args.generation or known_generation + 1
    generator = requirement.get("generator") or args.service
    if args.service == "host-age":
        generator = "host-age"

    if args.dry_run:
        print(
            f"Would rotate {args.node}/{args.service} to generation {generation} "
            f"in {requirement.get('sourceLedger') or source_ledger_for_service(args.service)}"
        )
        return 0

    try:
        if generator == "host-age":
            public_key, backup = rotate_host_age_key(args.node, args.flake)
            update_host_age_recipient_file(
                args.flake, args.node, public_key, generation=generation
            )
            stage_flake_paths(args.flake, [host_age_recipients_path(args.flake)])
            print(
                f"Rotated host-age recipient for {args.node} to generation {generation}"
            )
            print(f"old key moved to {backup}")
        elif generator == "ipns-publisher":
            private_ledger = requirement.get("privateLedger")
            if not private_ledger:
                raise ValueError(
                    f"{args.node}/{args.service} requirement has no privateLedger"
                )
            ipns_name, private_key = generate_ipns_key()
            update_sops_string_map(
                flake_root(args.flake) / private_ledger,
                args.node,
                private_key,
                args.sops_age_key_file,
                flake=args.flake,
            )
            record = generated_identity_record(
                args.service, args.node, {"ipnsName": ipns_name}
            )
            record["generation"] = generation
            update_identity_source_file(args.flake, args.service, args.node, record)
            stage_flake_paths(
                args.flake,
                [
                    identity_source_path(args.flake, args.service),
                    flake_root(args.flake) / private_ledger,
                ],
            )
            print(
                f"Rotated stable IPNS publishing identity for {args.node} "
                f"to generation {generation}: {ipns_name}"
            )
        elif generator == "onion-mirror":
            payload = capture_onion_mirror_identity(args.node, args.flake)
            record = generated_identity_record(args.service, args.node, payload)
            record["generation"] = generation
            update_identity_source_file(args.flake, args.service, args.node, record)
            stage_flake_paths(
                args.flake, [identity_source_path(args.flake, args.service)]
            )
            print(
                f"Rotated onion mirror identity for {args.node} "
                f"to generation {generation}: {payload['onionAddress']}"
            )
        elif generator == "status-ipns":
            private_ledger = requirement.get("privateLedger")
            sops_key = None
            sops_path = None
            try:
                ipns_name = capture_status_ipns_name(args.node, args.flake)
            except subprocess.CalledProcessError:
                if not private_ledger:
                    raise
                host_role = (
                    (
                        ((inventory.get("hosts") or {}).get(args.node) or {}).get(
                            "org"
                        )
                        or {}
                    )
                    .get("clusterIdentity", {})
                    .get("role")
                )
                if host_role != "leader":
                    print(
                        f"Node-local status IPNS rotation failed for {args.node}; "
                        "SOPS fallback is only supported for leader hosts.",
                        file=sys.stderr,
                    )
                    return 1
                ipns_name, private_key = generate_ipns_key()
                sops_key = f"{args.node}-status-ipns"
                sops_path = private_ledger
                update_sops_string_map(
                    flake_root(args.flake) / private_ledger,
                    sops_key,
                    private_key,
                    args.sops_age_key_file,
                    flake=args.flake,
                )
            record = generated_identity_record(
                args.service,
                args.node,
                {
                    "ipnsName": ipns_name,
                    "keyName": status.default_status_key_name(args.node),
                    "sopsPath": sops_path,
                    "sopsKey": sops_key,
                },
            )
            record["generation"] = generation
            update_identity_source_file(args.flake, args.service, args.node, record)
            paths = [identity_source_path(args.flake, args.service)]
            if sops_path:
                paths.append(flake_root(args.flake) / sops_path)
            stage_flake_paths(args.flake, paths)
            print(
                f"Rotated status IPNS identity for {args.node} "
                f"to generation {generation}: {ipns_name}"
            )
        elif generator == "leader-user-ssh":
            private_ledger = requirement.get("privateLedger")
            if not private_ledger:
                raise ValueError(
                    f"{args.node}/{args.service} requirement has no privateLedger"
                )
            user_name, target_path = leader_user_for_host(inventory, args.node)
            public_key, private_key = generate_ssh_key(
                f"{user_name}@{args.node} cluster leader"
            )
            update_sops_string_map(
                flake_root(args.flake) / private_ledger,
                f"{args.node}-leader-user-ssh",
                private_key,
                args.sops_age_key_file,
                flake=args.flake,
            )
            record = generated_identity_record(
                args.service,
                args.node,
                {
                    "sshPublicKey": public_key,
                    "targetPath": target_path,
                    "user": user_name,
                },
            )
            record["generation"] = generation
            update_identity_source_file(args.flake, args.service, args.node, record)
            stage_flake_paths(
                args.flake,
                [
                    identity_source_path(args.flake, args.service),
                    flake_root(args.flake) / private_ledger,
                ],
            )
            print(
                f"Rotated leader SSH identity for {user_name}@{args.node} "
                f"to generation {generation}"
            )
        elif generator == "yggdrasil":
            payload = capture_yggdrasil_public(args.node, args.flake)
            record = generated_identity_record(args.service, args.node, payload)
            record["generation"] = generation
            update_identity_source_file(args.flake, args.service, args.node, record)
            stage_flake_paths(
                args.flake, [identity_source_path(args.flake, args.service)]
            )
            print(
                f"Rotated Yggdrasil public identity for {args.node} "
                f"to generation {generation}"
            )
        elif generator == "ssh-host":
            payload = {"sshHostKey": capture_ssh_host_key(args.node, args.flake)}
            record = generated_identity_record(args.service, args.node, payload)
            record["generation"] = generation
            update_identity_source_file(args.flake, args.service, args.node, record)
            stage_flake_paths(
                args.flake, [identity_source_path(args.flake, args.service)]
            )
            print(
                f"Rotated SSH host key for {args.node} to generation {generation}"
            )
        elif generator == "radicle":
            payload = {"radicleNodeId": capture_radicle_node_id(args.node, args.flake)}
            record = generated_identity_record(args.service, args.node, payload)
            record["generation"] = generation
            update_identity_source_file(args.flake, args.service, args.node, record)
            stage_flake_paths(
                args.flake, [identity_source_path(args.flake, args.service)]
            )
            print(
                f"Rotated Radicle node id for {args.node} to generation {generation}"
            )
        elif generator == "git-annex":
            payload = derive_git_annex_payload(inventory, args.node)
            record = generated_identity_record(args.service, args.node, payload)
            record["generation"] = generation
            update_identity_source_file(args.flake, args.service, args.node, record)
            stage_flake_paths(
                args.flake, [identity_source_path(args.flake, args.service)]
            )
            print(
                f"Rotated git-annex endpoint for {args.node} to generation {generation}"
            )
        else:
            print(
                f"automatic rotation is not implemented for {args.node}/{args.service}",
                file=sys.stderr,
            )
            return 1
    except subprocess.CalledProcessError as error:
        print(
            f"Failed to rotate {args.node}/{args.service}: "
            f"{process_error_message(error)}",
            file=sys.stderr,
        )
        return 1

    if args.publish and requirement.get("registryPublish", True):
        publish_args = argparse.Namespace(
            registry=args.registry,
            out=args.out,
            policy=args.policy,
            flake=args.flake,
            service=[args.service],
            node=[args.node],
            generation=generation,
            state=None,
            leader=args.leader,
            leader_key=args.leader_key,
            signature=args.signature,
            signing_key=args.signing_key,
            allow_duplicate=False,
            allow_cross_leader_publish=False,
            burn_stale=getattr(args, "burn_stale", True),
            burn_guarded_stale=getattr(args, "burn_guarded_stale", False),
            no_commit=args.no_commit,
            no_reconcile=args.no_reconcile,
            fetch=True,
            push=args.publish_push,
            remote=[],
            notify=args.notify,
        )
        try:
            publish_result = publish_generated_identities(publish_args)
        except (PermissionError, RuntimeError) as error:
            print(f"Could not publish rotated identity: {error}", file=sys.stderr)
            return 1
        if publish_result != 0:
            return publish_result

    return 0


def cmd_identity_generate_missing(args) -> int:
    inventory = transport.inventory(args.flake)
    services = normalize_filter_values(args.service)
    nodes = normalize_filter_values(args.node)
    if getattr(args, "all", False):
        if nodes:
            print("--all cannot be combined with --node", file=sys.stderr)
            return 2
        nodes = []
    report = build_identity_matrix(inventory, services, nodes)
    missing = report["missing"]

    if not missing:
        print("No desired identities are missing.")
        return 0

    generated: list[tuple[str, str]] = []
    publishable_generated: list[tuple[str, str]] = []
    unsupported: list[tuple[str, str]] = []
    failed: list[tuple[str, str, str]] = []

    def failed_process_message(error: subprocess.CalledProcessError) -> str:
        details = (error.stderr or error.stdout or "").strip()
        if details:
            return f"{error.cmd!r} exited {error.returncode}: {details}"
        return f"{error.cmd!r} exited {error.returncode}"

    for item in missing:
        node = item["node"]
        service = item["service"]
        requirement = item.get("requirement") or {}
        generator = requirement.get("generator") or service
        if generator == "host-age":
            if args.dry_run:
                print(
                    f"Would bootstrap host-age for {node} -> {source_ledger_for_service(service)}"
                )
            else:
                try:
                    public_key = ensure_host_age_key(node, args.flake)
                except subprocess.CalledProcessError as error:
                    failed.append((node, service, failed_process_message(error)))
                    continue
                update_host_age_recipient_file(args.flake, node, public_key)
                print(f"Generated host-age recipient for {node}")
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        if generator == "ipns-publisher":
            private_ledger = requirement.get("privateLedger")
            if not private_ledger:
                raise ValueError(f"{node}/{service} requirement has no privateLedger")
            if args.dry_run:
                print(
                    f"Would generate stable IPNS publishing key for {node} -> "
                    f"{item['sourceLedger']} + {private_ledger}"
                )
            else:
                ipns_name, private_key = generate_ipns_key()
                update_sops_string_map(
                    flake_root(args.flake) / private_ledger,
                    node,
                    private_key,
                    args.sops_age_key_file,
                    flake=args.flake,
                )
                source_path = identity_source_path(args.flake, service)
                update_identity_source_file(
                    args.flake,
                    service,
                    node,
                    generated_identity_record(service, node, {"ipnsName": ipns_name}),
                )
                stage_flake_paths(
                    args.flake,
                    [
                        source_path,
                        flake_root(args.flake) / private_ledger,
                    ],
                )
                print(
                    f"Generated stable IPNS publishing identity for {node}: {ipns_name}"
                )
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        if generator == "onion-mirror":
            if args.dry_run:
                print(
                    f"Would capture onion mirror identity for {node} -> "
                    f"{source_ledger_for_service(service)}"
                )
            else:
                try:
                    payload = capture_onion_mirror_identity(node, args.flake)
                except subprocess.CalledProcessError as error:
                    failed.append((node, service, failed_process_message(error)))
                    continue
                update_identity_source_file(
                    args.flake,
                    service,
                    node,
                    generated_identity_record(service, node, payload),
                )
                print(
                    f"Captured onion mirror identity for {node}: "
                    f"{payload['onionAddress']}"
                )
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        if generator == "status-ipns":
            private_ledger = requirement.get("privateLedger")
            if args.dry_run:
                print(
                    f"Would ensure node-local status IPNS key for {node} -> "
                    f"{item['sourceLedger']}"
                )
            else:
                sops_key = None
                sops_path = None
                source_path = identity_source_path(args.flake, service)
                try:
                    ipns_name = capture_status_ipns_name(node, args.flake)
                    print(
                        f"Enrolled node-local status IPNS identity for {node}: {ipns_name}"
                    )
                except subprocess.CalledProcessError as error:
                    if not private_ledger:
                        raise
                    host_role = (
                        (
                            ((inventory.get("hosts") or {}).get(node) or {}).get("org")
                            or {}
                        )
                        .get("clusterIdentity", {})
                        .get("role")
                    )
                    if host_role != "leader":
                        print(
                            f"Node-local status IPNS enrollment failed for {node}; "
                            "SOPS fallback is only supported for leader hosts because "
                            f"{private_ledger} is encrypted to leader recipients."
                        )
                        unsupported.append((node, service))
                        continue
                    print(
                        f"Node-local status IPNS enrollment failed for {node}; "
                        "generating SOPS-backed key for deployment."
                    )
                    ipns_name, private_key = generate_ipns_key()
                    sops_key = f"{node}-status-ipns"
                    sops_path = private_ledger
                    update_sops_string_map(
                        flake_root(args.flake) / private_ledger,
                        sops_key,
                        private_key,
                        args.sops_age_key_file,
                        flake=args.flake,
                    )
                    print(
                        f"Generated deployable status IPNS identity for {node}: "
                        f"{ipns_name} ({error.returncode})"
                    )
                source_path = identity_source_path(args.flake, service)
                update_identity_source_file(
                    args.flake,
                    service,
                    node,
                    generated_identity_record(
                        service,
                        node,
                        {
                            "ipnsName": ipns_name,
                            "keyName": status.default_status_key_name(node),
                            "sopsPath": sops_path,
                            "sopsKey": sops_key,
                        },
                    ),
                )
                paths = [source_path]
                if sops_path:
                    paths.append(flake_root(args.flake) / sops_path)
                stage_flake_paths(args.flake, paths)
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        if generator == "leader-user-ssh":
            private_ledger = requirement.get("privateLedger")
            if not private_ledger:
                raise ValueError(f"{node}/{service} requirement has no privateLedger")
            user_name, target_path = leader_user_for_host(inventory, node)
            sops_key = f"{node}-leader-user-ssh"
            if args.dry_run:
                print(
                    f"Would generate leader SSH identity for {user_name}@{node} -> "
                    f"{item['sourceLedger']} + {private_ledger}"
                )
            else:
                public_key, private_key = generate_ssh_key(
                    f"{user_name}@{node} cluster leader"
                )
                update_sops_string_map(
                    flake_root(args.flake) / private_ledger,
                    sops_key,
                    private_key,
                    args.sops_age_key_file,
                    flake=args.flake,
                )
                source_path = identity_source_path(args.flake, service)
                update_identity_source_file(
                    args.flake,
                    service,
                    node,
                    generated_identity_record(
                        service,
                        node,
                        {
                            "sshPublicKey": public_key,
                            "targetPath": target_path,
                            "user": user_name,
                        },
                    ),
                )
                stage_flake_paths(
                    args.flake,
                    [
                        source_path,
                        flake_root(args.flake) / private_ledger,
                    ],
                )
                print(f"Generated leader SSH identity for {user_name}@{node}")
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        if generator == "yggdrasil":
            if args.dry_run:
                print(
                    f"Would discover Yggdrasil identity for {node} -> {source_ledger_for_service(service)}"
                )
            else:
                try:
                    payload = capture_yggdrasil_public(node, args.flake)
                except subprocess.CalledProcessError as error:
                    failed.append((node, service, failed_process_message(error)))
                    continue
                update_identity_source_file(
                    args.flake,
                    service,
                    node,
                    generated_identity_record(service, node, payload),
                )
                print(f"Generated Yggdrasil public identity for {node}")
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        if generator == "ssh-host":
            if args.dry_run:
                print(
                    f"Would capture SSH host key for {node} -> {source_ledger_for_service(service)}"
                )
            else:
                try:
                    payload = {"sshHostKey": capture_ssh_host_key(node, args.flake)}
                except subprocess.CalledProcessError as error:
                    failed.append((node, service, failed_process_message(error)))
                    continue
                update_identity_source_file(
                    args.flake,
                    service,
                    node,
                    generated_identity_record(service, node, payload),
                )
                print(f"Captured SSH host key for {node}")
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        if generator == "radicle":
            if args.dry_run:
                print(
                    f"Would capture Radicle node id for {node} -> {source_ledger_for_service(service)}"
                )
            else:
                try:
                    payload = {
                        "radicleNodeId": capture_radicle_node_id(node, args.flake)
                    }
                except subprocess.CalledProcessError as error:
                    failed.append((node, service, failed_process_message(error)))
                    continue
                update_identity_source_file(
                    args.flake,
                    service,
                    node,
                    generated_identity_record(service, node, payload),
                )
                print(f"Captured Radicle node id for {node}")
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        if generator == "git-annex":
            if args.dry_run:
                print(
                    f"Would derive git-annex endpoint for {node} -> {source_ledger_for_service(service)}"
                )
            else:
                payload = derive_git_annex_payload(inventory, node)
                update_identity_source_file(
                    args.flake,
                    service,
                    node,
                    generated_identity_record(service, node, payload),
                )
                print(f"Derived git-annex endpoint for {node}")
            generated.append((node, service))
            if requirement.get("registryPublish", True):
                publishable_generated.append((node, service))
            continue

        unsupported.append((node, service))

    if unsupported:
        print("\nStill manual:")
        for node, service in unsupported:
            print(f"  - {node}/{service} -> {source_ledger_for_service(service)}")
        return 1

    if failed:
        print("\nFailed automatic generation:")
        for node, service, message in failed:
            print(f"  - {node}/{service}: {message}")
        return 1

    if publishable_generated and not args.dry_run and args.publish:
        generated_nodes = sorted({node for node, _service in publishable_generated})
        generated_services = sorted(
            {service for _node, service in publishable_generated}, key=service_sort_key
        )
        publish_args = argparse.Namespace(
            registry=args.registry,
            out=args.out,
            policy=args.policy,
            flake=args.flake,
            service=generated_services,
            node=generated_nodes,
            generation=None,
            state=None,
            leader=args.leader,
            leader_key=args.leader_key,
            signature=args.signature,
            signing_key=args.signing_key,
            allow_duplicate=False,
            no_commit=args.no_commit,
            no_reconcile=args.no_reconcile,
            fetch=True,
            push=args.publish_push,
            remote=[],
            notify=args.notify,
        )
        try:
            publish_result = publish_generated_identities(publish_args)
        except (PermissionError, RuntimeError) as error:
            print(f"Could not publish generated identities: {error}", file=sys.stderr)
            return 1
        if publish_result != 0:
            return publish_result

    if unsupported:
        return 1
    return 0


def public_from_inventory_data(inventory: dict, node: str, service: str) -> dict:
    identity_record = (
        ((inventory.get("identities") or {}).get("services") or {}).get(service) or {}
    ).get(node)
    if identity_record:
        public = public_from_identity_record(identity_record)
        if public:
            return public
    if service == "yggdrasil":
        ygg_node = (
            ((inventory.get("networks") or {}).get("privateYggdrasil") or {}).get(
                "nodes"
            )
            or {}
        ).get(node) or {}
        public = {}
        public_key = ygg_node.get("publicKey")
        address = ygg_node.get("address")
        deploy_host = ygg_node.get("deployHost") or address
        generated_at = (
            ygg_node.get("generatedAt")
            or ygg_node.get("keyGeneratedAt")
            or ygg_node.get("sourceTimestamp")
        )
        if public_key:
            public["yggdrasilPublicKey"] = public_key
        if address:
            public["yggdrasilAddress"] = address
        if deploy_host:
            public["deployHost"] = deploy_host
        if generated_at:
            public["keyGeneratedAt"] = generated_at
        if not public:
            raise ValueError(f"inventory has no public Yggdrasil identity for {node!r}")
        return public
    if service == "git-annex":
        return derive_git_annex_payload(inventory, node)
    raise ValueError(f"--from-inventory is not implemented for service {service!r}")


def public_from_inventory(flake: str, node: str, service: str) -> dict:
    return public_from_inventory_data(transport.inventory(flake), node, service)


def registry_already_has_identity(
    registry_path: Path,
    node: str,
    service: str,
    generation: int,
    state: str,
    public: dict,
    private_delivery: dict | None,
) -> bool:
    normalized_public = dict(public)
    fingerprint = registry.public_identity_fingerprint(service, normalized_public)
    if fingerprint:
        normalized_public["fingerprint"] = fingerprint
    for _path, event in registry.load_events(registry_path):
        subject = event.get("subject") or {}
        if (
            subject.get("node") == node
            and subject.get("service") == service
            and event.get("generation") == generation
            and event.get("state") == state
            and (event.get("public") or {}) == normalized_public
            and event.get("privateDelivery") == private_delivery
        ):
            return True
    return False


def event_reference(event: dict) -> dict:
    return {
        "eventHash": event["eventHash"],
        "leader": event["leader"],
        "generation": event["generation"],
    }


def find_event_by_hash(registry_path: Path, event_hash: str) -> dict | None:
    for _path, event in registry.identity_events(registry.load_events(registry_path)):
        if event.get("eventHash") == event_hash:
            return event
    return None


def observed_root_cid(policy: dict, event: dict) -> str | None:
    head = (registry.load_checkpoint(policy).get("heads") or {}).get(event["leader"])
    if isinstance(head, dict) and isinstance(head.get("cid"), str):
        return head["cid"]
    return None


def accepted_identity_registry_path(policy: dict) -> Path:
    configured = (policy.get("registry") or {}).get("acceptedRegistryPath")
    return Path(configured or "/var/lib/cluster-identity/accepted-registry")


def identity_publish_authority_error(policy: dict, leader: str, allow_cross_leader: bool = False) -> str | None:
    local_host = policy.get("hostName")
    if allow_cross_leader or not local_host or leader == local_host:
        return None
    return (
        f"refusing to publish identity events as leader {leader!r} from local host {local_host!r}; "
        "run publication on the signing leader or pass --allow-cross-leader-publish after an explicit deploy"
    )


def write_supersedence_record(
    *,
    registry_path: Path,
    policy: dict,
    leader: str,
    leader_key_arg: str | None,
    superseding_event: dict,
    superseded_event: dict,
    reason: str,
    signing_key: Path | None,
    observed_root: str | None = None,
) -> Path | None:
    if superseding_event.get("eventHash") == superseded_event.get("eventHash"):
        raise ValueError("an identity event cannot supersede itself")
    if superseding_event.get("subject") != superseded_event.get("subject"):
        raise ValueError("supersedence requires events for the same node/service")
    if superseding_event.get("payloadHash") == superseded_event.get("payloadHash"):
        raise ValueError("supersedence requires conflicting payloads")
    for _path, existing in registry.supersedence_records(
        registry.load_events(registry_path)
    ):
        if (
            (existing.get("superseding") or {}).get("eventHash")
            == superseding_event["eventHash"]
            and (existing.get("superseded") or {}).get("eventHash")
            == superseded_event["eventHash"]
        ):
            return None

    leader_public_key = leader_key_arg or leader_key(policy, leader)
    record = {
        "schema": registry.SUPERSEDENCE_SCHEMA,
        "eventId": new_event_id("supersedence"),
        "leader": leader,
        "leaderKeyId": key_fingerprint(leader_public_key),
        "policyGeneration": int(
            (policy.get("policy") or policy).get("policyGeneration", 1)
        ),
        "clusterId": registry.cluster_id(policy),
        "subject": dict(superseding_event["subject"]),
        "superseding": event_reference(superseding_event),
        "supersedingEvent": dict(superseding_event),
        "superseded": event_reference(superseded_event),
        "supersededEvent": dict(superseded_event),
        "observedRootCid": observed_root
        if observed_root is not None
        else observed_root_cid(policy, superseded_event),
        "reason": reason,
        "createdAt": now_utc(),
    }
    registry.finalize_supersedence(registry_path, record)
    attach_signature(record, signing_key, None, policy)
    path = registry.canonical_event_path(registry_path, record)
    write_json(path, record)
    return path


def write_public_identity_event(
    *,
    registry_path: Path,
    policy: dict,
    leader: str,
    leader_key_arg: str | None,
    node: str,
    service: str,
    generation: int,
    state: str,
    public: dict,
    private_delivery: dict | None,
    supersedes: list[str],
    signature: str | None,
    signing_key: Path | None,
    no_commit: bool,
    allow_duplicate: bool,
    auto_supersede: bool = True,
    burn_same_leader_previous: bool = False,
    observed_registry_path: Path | None = None,
) -> Path | None:
    if not allow_duplicate and registry_already_has_identity(
        registry_path, node, service, generation, state, public, private_delivery
    ):
        print(
            f"Registry already has {node}/{service} generation {generation} in state {state}"
        )
        return None
    existing_by_hash: dict[str, dict] = {}
    for source in [registry_path, observed_registry_path]:
        if source is None or not source.exists():
            continue
        for _path, existing in registry.identity_events(registry.load_events(source)):
            if (
                existing.get("state") != "burned"
                and existing.get("leader") != leader
                and existing.get("subject") == {"node": node, "service": service}
                and isinstance(existing.get("generation"), int)
                and existing["generation"] >= generation
                and isinstance(existing.get("eventHash"), str)
            ):
                existing_by_hash[existing["eventHash"]] = existing
    existing_events = list(existing_by_hash.values())
    event_id = new_event_id("identity")
    try:
        leader_public_key = leader_key_arg or leader_key(policy, leader)
    except ValueError as error:
        raise ValueError(str(error)) from error
    event = {
        "schema": "cluster.identity.event.v1",
        "eventId": event_id,
        "leader": leader,
        "policyGeneration": int(
            (policy.get("policy") or policy).get("policyGeneration", 1)
        ),
        "subject": {
            "node": node,
            "service": service,
        },
        "generation": generation,
        "state": state,
        "public": public,
        "privateDelivery": private_delivery,
        "supersedes": supersedes,
        "createdAt": now_utc(),
    }
    path = prepare_event(
        registry_path, event, policy, leader_public_key, signing_key, signature
    )
    appended = [path]
    try:
        if auto_supersede:
            for existing in existing_events:
                if existing.get("payloadHash") == event.get("payloadHash"):
                    continue
                resolution_path = write_supersedence_record(
                    registry_path=registry_path,
                    policy=policy,
                    leader=leader,
                    leader_key_arg=leader_key_arg,
                    superseding_event=event,
                    superseded_event=existing,
                    reason="observed preexisting conflict while publishing new entry",
                    signing_key=signing_key,
                )
                if resolution_path is not None:
                    appended.append(resolution_path)
        if burn_same_leader_previous:
            for old_event in previous_same_leader_burn_targets(
                registry_path=registry_path,
                observed_registry_path=observed_registry_path,
                leader=leader,
                node=node,
                service=service,
                generation=generation,
                new_public=public,
            ):
                old_generation = identity_generation(old_event)
                fingerprint = registry.public_identity_fingerprint(
                    service, old_event.get("public") or {}
                )
                if old_generation is None or not fingerprint:
                    continue
                burn_path = append_burn_event(
                    registry_path=registry_path,
                    policy=policy,
                    leader=leader,
                    leader_key_arg=leader_key_arg,
                    node=node,
                    service=service,
                    generation=old_generation,
                    fingerprint=fingerprint,
                    reason=(
                        "same leader rotated a newer generation for this "
                        "identity"
                    ),
                    signing_key=signing_key,
                )
                appended.append(burn_path)
        failures = registry.validate_registry(registry_path, policy)
        if failures:
            for failure in failures:
                print(f"- {failure}", file=sys.stderr)
            raise ValueError("registry validation failed after writing identity event")
    except Exception:
        for appended_path in reversed(appended):
            appended_path.unlink(missing_ok=True)
        raise
    commit(
        registry_path,
        f"identity publish {node} {service} gen {generation}",
        not no_commit,
    )
    return path


def cmd_identity_publish_public(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    authority_error = identity_publish_authority_error(
        policy,
        leader,
        getattr(args, "allow_cross_leader_publish", False),
    )
    if authority_error:
        print(authority_error, file=sys.stderr)
        return 1
    public = (
        public_from_inventory(args.flake, args.node, args.service)
        if args.from_inventory
        else {}
    )
    if args.ssh_host_key:
        public["sshHostKey"] = args.ssh_host_key
    if args.yggdrasil_public_key:
        public["yggdrasilPublicKey"] = args.yggdrasil_public_key
    if args.yggdrasil_address:
        public["yggdrasilAddress"] = args.yggdrasil_address
    if args.deploy_host:
        public["deployHost"] = args.deploy_host
    if args.radicle_node_id:
        public["radicleNodeId"] = args.radicle_node_id
    if args.git_annex_endpoint:
        public["gitAnnexEndpoint"] = args.git_annex_endpoint
    if not public:
        print(
            "No public identity fields were provided. Use --from-inventory or pass service-specific public fields.",
            file=sys.stderr,
        )
        return 1

    try:
        path = write_public_identity_event(
            registry_path=args.registry,
            policy=policy,
            leader=leader,
            leader_key_arg=args.leader_key,
            node=args.node,
            service=args.service,
            generation=args.generation,
            state=args.state,
            public=public,
            private_delivery=None,
            supersedes=args.supersedes,
            signature=args.signature,
            signing_key=args.signing_key,
            no_commit=args.no_commit,
            allow_duplicate=args.allow_duplicate,
            observed_registry_path=accepted_identity_registry_path(policy),
        )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    if path is not None:
        print(path)
    return 0


def cmd_identity_publish_inventory(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    authority_error = identity_publish_authority_error(
        policy,
        leader,
        getattr(args, "allow_cross_leader_publish", False),
    )
    if authority_error:
        print(authority_error, file=sys.stderr)
        return 1
    inventory = transport.inventory(args.flake)
    nodes = sorted(
        (
            ((inventory.get("networks") or {}).get("privateYggdrasil") or {}).get(
                "nodes"
            )
            or {}
        ).keys()
    )
    published = 0
    failed = 0
    for node in nodes:
        try:
            public = public_from_inventory_data(inventory, node, args.service)
        except ValueError:
            continue
        try:
            path = write_public_identity_event(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                node=node,
                service=args.service,
                generation=args.generation,
                state=args.state,
                public=public,
                private_delivery=None,
                supersedes=[],
                signature=args.signature,
                signing_key=args.signing_key,
                no_commit=args.no_commit,
                allow_duplicate=args.allow_duplicate,
                observed_registry_path=accepted_identity_registry_path(policy),
            )
        except ValueError as error:
            print(error, file=sys.stderr)
            failed += 1
            continue
        if path is not None:
            published += 1
            print(path)
    print(
        f"Published {published} {args.service} public identity event(s) from flake inventory"
    )
    if failed:
        print(f"Failed to publish {failed} identity event(s)", file=sys.stderr)
        return 1
    return 0


def cmd_identity_publish(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    authority_error = identity_publish_authority_error(
        policy,
        leader,
        getattr(args, "allow_cross_leader_publish", False),
    )
    if authority_error:
        print(authority_error, file=sys.stderr)
        return 1
    transports = (policy.get("registry") or {}).get("transports") or {}
    ipfs_transport = bool(transports.get("ipfs", False))
    git_transport = any(
        bool(transports.get(name, False))
        for name in ["gitSshYggdrasil", "radicle", "fallbackSsh"]
    )
    ensure_registry_git_repo(args.registry)
    if args.fetch and git_transport:
        transport.git_fetch_all(args.registry, policy)
    inventory = transport.inventory(args.flake)
    services = normalize_filter_values(args.service)
    nodes = normalize_filter_values(args.node)
    desired_records = {
        (node, service): {
            "generation": generation,
            "public": public,
        }
        for (
            node,
            service,
            _record,
            public,
            _private_delivery,
            generation,
            _state,
        ) in flake_identity_records(inventory)
        if isinstance(generation, int)
    }
    published = 0
    unchanged = 0
    failed = 0
    for (
        node,
        service,
        record,
        public,
        private_delivery,
        record_generation,
        record_state,
    ) in flake_identity_records(inventory, services, nodes):
        generation = (
            args.generation if args.generation is not None else record_generation
        )
        state = args.state or record_state
        if not isinstance(generation, int):
            print(
                f"Skipping {node}/{service}: generation is not an integer",
                file=sys.stderr,
            )
            failed += 1
            continue
        try:
            path = write_public_identity_event(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                node=node,
                service=service,
                generation=generation,
                state=state,
                public=public,
                private_delivery=private_delivery,
                supersedes=[],
                signature=args.signature,
                signing_key=args.signing_key,
                no_commit=True,
                allow_duplicate=args.allow_duplicate,
                burn_same_leader_previous=getattr(
                    args, "burn_same_leader_previous", False
                ),
                observed_registry_path=accepted_identity_registry_path(policy),
            )
        except ValueError as error:
            print(error, file=sys.stderr)
            failed += 1
            continue
        if path is None:
            unchanged += 1
        else:
            published += 1
            print(path)
    stale_burn_paths: list[Path] = []
    if getattr(args, "burn_stale", True):
        try:
            stale_targets = same_leader_stale_burn_targets(
                registry_path=args.registry,
                observed_registry_path=accepted_identity_registry_path(policy),
                leader=leader,
                desired=desired_records,
                include_guarded=getattr(args, "burn_guarded_stale", False),
            )
            stale_burn_paths = append_stale_burn_events(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                signing_key=args.signing_key,
                targets=stale_targets,
            )
        except ValueError as error:
            print(error, file=sys.stderr)
            failed += 1
        for path in stale_burn_paths:
            print(path)
        if stale_burn_paths:
            failures = registry.validate_registry(args.registry, policy)
            if failures:
                for failure in failures:
                    print(f"- {failure}", file=sys.stderr)
                for path in reversed(stale_burn_paths):
                    path.unlink(missing_ok=True)
                stale_burn_paths = []
                failed += 1
    if published:
        commit(args.registry, "identity publish flake ledger", not args.no_commit)
    elif stale_burn_paths:
        commit(args.registry, "identity burn stale leader claims", not args.no_commit)
    if not args.no_reconcile:
        try:
            registry.reconcile(args.registry, args.out, policy)
        except PermissionError as error:
            print(f"Skipping local materialization: {error}", file=sys.stderr)
    pushed: list[str] = []
    published_head: dict | None = None
    if args.push and ipfs_transport:
        published_head = snapshot.publish_snapshot(
            args.registry,
            _snapshot_path(policy, None),
            policy,
            leader,
            signing_key_path(policy, args.signing_key),
        )
    elif args.push and git_transport:
        pushed = transport.git_push_remotes(args.registry, args.remote, policy)
    if args.notify:
        targets = resolve_hosts_arg(args.node, inventory)
        notify.notify_targets(targets, args.out, args.flake)
    print(f"Published {published} flake identity event(s); {unchanged} already current")
    if pushed:
        print(f"Pushed registry remotes: {', '.join(pushed)}")
    elif published_head:
        print(
            f"Published registry root {published_head['rootCid']} through {published_head['ipnsName']}"
        )
    elif args.push and git_transport:
        print("No Git remotes configured for registry push")
    elif args.push:
        print("No enabled registry publication transport")
    if failed:
        print(f"Failed to publish {failed} identity event(s)", file=sys.stderr)
        return 1
    return 0


def find_event(
    registry_path: Path, node: str, service: str, generation: int
) -> dict | None:
    for _path, event in registry.load_events(registry_path):
        subject = event.get("subject") or {}
        if (
            subject.get("node") == node
            and subject.get("service") == service
            and event.get("generation") == generation
        ):
            return event
    return None


def resolution_event(
    registry_path: Path,
    policy: dict,
    event_hash: str,
) -> dict | None:
    event = find_event_by_hash(registry_path, event_hash)
    if event is not None:
        return event
    accepted = accepted_identity_registry_path(policy)
    if accepted != registry_path and accepted.exists():
        return find_event_by_hash(accepted, event_hash)
    return None


def cmd_identity_resolve(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    ensure_registry_git_repo(args.registry)
    winner = resolution_event(args.registry, policy, args.winner_event)
    loser = resolution_event(args.registry, policy, args.loser_event)
    if winner is None:
        print(f"Unknown winning event hash: {args.winner_event}", file=sys.stderr)
        return 1
    if loser is None:
        print(f"Unknown superseded event hash: {args.loser_event}", file=sys.stderr)
        return 1
    try:
        path = write_supersedence_record(
            registry_path=args.registry,
            policy=policy,
            leader=leader,
            leader_key_arg=args.leader_key,
            superseding_event=winner,
            superseded_event=loser,
            reason=args.reason,
            signing_key=args.signing_key,
            observed_root=args.observed_root_cid,
        )
        failures = registry.validate_registry(args.registry, policy)
        if failures:
            raise ValueError(
                "registry validation failed after supersedence:\n"
                + "\n".join(f"- {failure}" for failure in failures)
            )
        registry.reconcile(args.registry, args.out, policy)
        if path is not None:
            commit(
                args.registry,
                f"identity resolve {winner['eventHash']} over {loser['eventHash']}",
                not args.no_commit,
            )
        if args.push and ((policy.get("registry") or {}).get("transports") or {}).get(
            "ipfs", False
        ):
            snapshot.publish_snapshot(
                args.registry,
                _snapshot_path(policy, None),
                policy,
                leader,
                signing_key_path(policy, args.signing_key),
            )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    if path is None:
        print("That supersedence record already exists")
    else:
        print(path)
    return 0


def cmd_identity_promote(args) -> int:
    base = find_event(args.registry, args.node, args.service, args.generation)
    if not base:
        print(
            f"No event found for {args.node}/{args.service} generation {args.generation}",
            file=sys.stderr,
        )
        return 1
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    event_id = new_event_id("identity")
    promoted = dict(base)
    try:
        for field in [
            "signature",
            "eventHash",
            "leaderSeq",
            "previousLeaderEventHash",
            "leaderKeyId",
        ]:
            promoted.pop(field, None)
        leader_public_key = args.leader_key or leader_key(policy, leader)
        promoted.update(
            {
                "eventId": event_id,
                "leader": leader,
                "state": "active",
                "supersedes": [base.get("eventId")],
                "createdAt": now_utc(),
            }
        )
        path = prepare_event(
            args.registry,
            promoted,
            policy,
            leader_public_key,
            args.signing_key,
            args.signature,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    failures = registry.validate_registry(args.registry, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    commit(
        args.registry,
        f"identity promote {args.node} {args.service} gen {args.generation}",
        not args.no_commit,
    )
    print(path)
    return 0


def cmd_identity_burn(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    event_id = new_event_id("burn")
    try:
        leader_public_key = args.leader_key or leader_key(policy, leader)
        event = {
            "schema": "cluster.identity.event.v1",
            "eventId": event_id,
            "leader": leader,
            "policyGeneration": int(
                (policy.get("policy") or policy).get("policyGeneration", 1)
            ),
            "subject": {
                "node": args.node,
                "service": args.service,
            },
            "generation": args.generation,
            "state": "burned",
            "burned": {
                "fingerprint": args.fingerprint,
                "reason": args.reason,
                "burnedAt": now_utc(),
                "scope": "subject-generation",
            },
            "createdAt": now_utc(),
        }
        path = prepare_event(
            args.registry,
            event,
            policy,
            leader_public_key,
            args.signing_key,
            args.signature,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    failures = registry.validate_registry(args.registry, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    commit(
        args.registry,
        f"identity burn {args.node} {args.service} gen {args.generation}",
        not args.no_commit,
    )
    print(path)
    return 0


def resolve_target(host: str, flake: str) -> tuple[str, str]:
    bootstrap = transport.host_bootstrap(flake).get(host, {})
    target_host = f"{host}-bootstrap" if bootstrap.get("targetHost") else host
    return target_host, bootstrap.get("sshUser") or "root"


def resolve_bootstrap_target(host: str, flake: str) -> tuple[str, str, str | None]:
    bootstrap = transport.host_bootstrap(flake).get(host, {})
    target_host = f"{host}-bootstrap" if bootstrap.get("targetHost") else host
    return (
        target_host,
        bootstrap.get("sshUser") or "root",
        bootstrap.get("identityFile"),
    )


def operator_hosts(inventory: dict) -> list[str]:
    bootstrap = inventory.get("hostBootstrap") or {}
    selected = [
        name
        for name, config in sorted(bootstrap.items())
        if isinstance(config, dict) and config.get("operatorCapable")
    ]
    if selected:
        return selected
    return sorted((inventory.get("hosts") or {}).keys())


def next_generation(registry_path: Path, node: str, service: str) -> int:
    highest = 0
    for _path, event in registry.load_events(registry_path):
        subject = event.get("subject") or {}
        generation = event.get("generation")
        if (
            subject.get("node") == node
            and subject.get("service") == service
            and isinstance(generation, int)
            and generation > highest
        ):
            highest = generation
    return highest + 1


def smoke_public_payload(run_id: str, phase: str, sequence: int, node: str) -> dict:
    return {
        "smokeRun": run_id,
        "smokePhase": phase,
        "smokeSequence": sequence,
        "smokeNode": node,
        "smokeToken": hashlib.sha256(
            f"{run_id}:{phase}:{sequence}:{node}".encode("utf-8")
        ).hexdigest()[:24],
    }


def smoke_fingerprint(run_id: str, service: str, node: str, generation: int) -> str:
    payload = f"{run_id}:{service}:{node}:{generation}"
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ssh_run(
    host: str, flake: str, remote_command: str, *, capture_output: bool = False
) -> subprocess.CompletedProcess:
    target_host, ssh_user, identity_file = resolve_bootstrap_target(host, flake)
    command = ["ssh"]
    if identity_file:
        command.extend(["-i", identity_file])
    command.extend(
        [
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "IdentityAgent=none",
            f"{ssh_user}@{target_host}",
            remote_command,
        ]
    )
    return subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )


def trigger_remote_fetch(hosts: list[str], flake: str) -> None:
    for host in hosts:
        completed = ssh_run(
            host, flake, "systemctl start cluster-identity-fetch-now.service"
        )
        if completed.returncode != 0:
            raise RuntimeError(f"failed to trigger cluster identity fetch on {host}")


def remote_event_matches(
    host: str,
    flake: str,
    remote_registry_path: str,
    relative_event_path: str,
    expected_state: str,
    expected_generation: int,
) -> bool:
    remote_file = f"{remote_registry_path.rstrip('/')}/{relative_event_path}"
    command = (
        f"test -f {shlex.quote(remote_file)} "
        f"&& grep -q '\"generation\": {expected_generation}' {shlex.quote(remote_file)} "
        f'&& grep -q \'"state": "{expected_state}"\' {shlex.quote(remote_file)}'
    )
    completed = ssh_run(host, flake, command, capture_output=True)
    return completed.returncode == 0


def wait_for_remote_event(
    hosts: list[str],
    flake: str,
    remote_registry_path: str,
    relative_event_path: str,
    expected_state: str,
    expected_generation: int,
    *,
    timeout_seconds: int = 90,
    interval_seconds: float = 2.0,
) -> None:
    deadline = time.time() + timeout_seconds
    pending = set(hosts)
    while pending and time.time() < deadline:
        resolved: list[str] = []
        for host in sorted(pending):
            if remote_event_matches(
                host,
                flake,
                remote_registry_path,
                relative_event_path,
                expected_state,
                expected_generation,
            ):
                resolved.append(host)
        for host in resolved:
            pending.discard(host)
        if pending:
            time.sleep(interval_seconds)
    if pending:
        waiting = ", ".join(sorted(pending))
        raise RuntimeError(
            f"timed out waiting for remote event {relative_event_path} on: {waiting}"
        )


def ensure_remote_registry_clean(
    hosts: list[str], flake: str, remote_registry_path: str
) -> None:
    for host in hosts:
        completed = ssh_run(
            host,
            flake,
            f"git -C {shlex.quote(remote_registry_path)} status --short",
            capture_output=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"failed to inspect remote registry status on {host}")
        if completed.stdout.strip():
            raise RuntimeError(
                f"remote registry worktree is dirty on {host}: {completed.stdout.strip()}"
            )


def prepare_remote_smoke_hosts(
    hosts: list[str], flake: str, remote_registry_path: str
) -> None:
    for host in hosts:
        command = (
            "systemctl stop cluster-identity-fetch.timer cluster-identity-push.timer 2>/dev/null || true; "
            f"git -C {shlex.quote(remote_registry_path)} stash push -m cluster-identity-smoke-prep state >/dev/null 2>&1 || true"
        )
        completed = ssh_run(host, flake, command)
        if completed.returncode != 0:
            raise RuntimeError(f"failed to prepare remote smoke host {host}")


def restore_remote_smoke_hosts(hosts: list[str], flake: str) -> None:
    for host in hosts:
        ssh_run(
            host,
            flake,
            "systemctl start cluster-identity-fetch.timer cluster-identity-push.timer 2>/dev/null || true",
        )


def remote_state_entry(
    host: str, flake: str, out: Path, state_file: str, node: str, service: str
) -> dict | None:
    quoted_out = shlex.quote(str(out))
    quoted_state = shlex.quote(state_file)
    command = (
        "PATH=/run/current-system/sw/bin:$PATH python3 - <<'PY'\n"
        "import json\n"
        f"path = {quoted_out!r} + '/' + {quoted_state!r}\n"
        f"node = {node!r}\n"
        f"service = {service!r}\n"
        "with open(path, 'r', encoding='utf-8') as handle:\n"
        "    data = json.load(handle)\n"
        "entry = (((data.get('nodes') or {}).get(node) or {}).get(service))\n"
        "print(json.dumps(entry))\n"
        "PY"
    )
    completed = ssh_run(host, flake, command, capture_output=True)
    if completed.returncode != 0 or not completed.stdout:
        return None
    payload = completed.stdout.strip()
    if not payload or payload == "null":
        return None
    return json.loads(payload)


def wait_for_remote_state(
    hosts: list[str],
    flake: str,
    out: Path,
    state_file: str,
    node: str,
    service: str,
    generation: int,
    *,
    fingerprint: str | None = None,
    timeout_seconds: int = 90,
    interval_seconds: float = 2.0,
) -> None:
    deadline = time.time() + timeout_seconds
    pending = set(hosts)
    while pending and time.time() < deadline:
        resolved: list[str] = []
        for host in sorted(pending):
            entry = remote_state_entry(host, flake, out, state_file, node, service)
            if not entry:
                continue
            if fingerprint is not None:
                burned = entry.get("burned") or {}
                if burned.get("fingerprint") == fingerprint:
                    resolved.append(host)
                continue
            if entry.get("generation") == generation:
                resolved.append(host)
        for host in resolved:
            pending.discard(host)
        if pending:
            time.sleep(interval_seconds)
    if pending:
        waiting = ", ".join(sorted(pending))
        raise RuntimeError(
            f"timed out waiting for {state_file} {node}/{service} generation {generation} on: {waiting}"
        )


def write_smoke_event(
    *,
    registry_path: Path,
    policy: dict,
    leader: str,
    leader_key_arg: str | None,
    signing_key: Path | None,
    node: str,
    service: str,
    generation: int,
    state: str,
    public: dict,
    supersedes: list[str] | None = None,
    no_commit: bool = False,
) -> Path | None:
    return write_public_identity_event(
        registry_path=registry_path,
        policy=policy,
        leader=leader,
        leader_key_arg=leader_key_arg,
        node=node,
        service=service,
        generation=generation,
        state=state,
        public=public,
        private_delivery=None,
        supersedes=supersedes or [],
        signature=None,
        signing_key=signing_key,
        no_commit=no_commit,
        allow_duplicate=False,
    )


def burn_smoke_event(
    *,
    registry_path: Path,
    policy: dict,
    leader: str,
    leader_key_arg: str | None,
    signing_key: Path | None,
    node: str,
    service: str,
    generation: int,
    fingerprint: str,
    reason: str,
    no_commit: bool = False,
) -> Path:
    event_id = new_event_id("burn")
    event = {
        "schema": "cluster.identity.event.v1",
        "eventId": event_id,
        "leader": leader,
        "policyGeneration": int(
            (policy.get("policy") or policy).get("policyGeneration", 1)
        ),
        "subject": {
            "node": node,
            "service": service,
        },
        "generation": generation,
        "state": "burned",
        "burned": {
            "fingerprint": fingerprint,
            "reason": reason,
            "burnedAt": now_utc(),
            "scope": "subject-generation",
        },
        "createdAt": now_utc(),
    }
    leader_public_key = leader_key_arg or leader_key(policy, leader)
    path = prepare_event(
        registry_path, event, policy, leader_public_key, signing_key, None
    )
    failures = registry.validate_registry(registry_path, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise RuntimeError("registry validation failed after burning smoke identity")
    commit(
        registry_path, f"identity burn {node} {service} gen {generation}", not no_commit
    )
    return path


def smoke_promote(
    *,
    registry_path: Path,
    policy: dict,
    leader: str,
    leader_key_arg: str | None,
    signing_key: Path | None,
    node: str,
    service: str,
    generation: int,
    no_commit: bool = False,
) -> Path:
    base = find_event(registry_path, node, service, generation)
    if not base:
        raise RuntimeError(
            f"no staged smoke event found for {node}/{service} generation {generation}"
        )
    promoted = dict(base)
    for field in [
        "signature",
        "eventHash",
        "leaderSeq",
        "previousLeaderEventHash",
        "leaderKeyId",
    ]:
        promoted.pop(field, None)
    promoted.update(
        {
            "eventId": new_event_id("identity"),
            "leader": leader,
            "state": "active",
            "supersedes": [base.get("eventId")],
            "createdAt": now_utc(),
        }
    )
    leader_public_key = leader_key_arg or leader_key(policy, leader)
    path = prepare_event(
        registry_path, promoted, policy, leader_public_key, signing_key, None
    )
    failures = registry.validate_registry(registry_path, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise RuntimeError("registry validation failed after promoting smoke identity")
    commit(
        registry_path,
        f"identity promote {node} {service} gen {generation}",
        not no_commit,
    )
    return path


def smoke_push_and_fetch(
    registry_path: Path, policy: dict, verify_hosts: list[str], flake: str
) -> None:
    pushed = smoke_push_remotes(registry_path, policy)
    if not pushed:
        raise RuntimeError("no Git remotes configured for smoke-test push")
    ensure_remote_registry_clean(
        verify_hosts,
        flake,
        policy.get("registryPath") or str(DEFAULT_REGISTRY),
    )


def smoke_remote_names(policy: dict) -> list[str]:
    fallback = [
        name for name in transport.policy_remotes(policy, "push") if "fallback" in name
    ]
    if fallback:
        return fallback
    return transport.policy_remotes(policy, "push")


def smoke_fetch_remotes(registry_path: Path, policy: dict) -> None:
    env = smoke_git_environment(policy)
    for remote in smoke_remote_names(policy):
        subprocess.run(
            ["git", "-C", str(registry_path), "fetch", remote, "--prune"],
            check=False,
            env=env,
        )


def smoke_git_environment(policy: dict) -> dict:
    transport_policy = (policy.get("registry") or {}).get("transport") or {}
    identity_file = transport_policy.get("identityFile")
    command = ["ssh"]
    if identity_file:
        command.extend(["-i", identity_file])
    command.extend(
        [
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "IdentityAgent=none",
            "-o",
            "BatchMode=yes",
            "-o",
            "PreferredAuthentications=publickey",
        ]
    )
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = " ".join(command)
    return env


def smoke_push_remotes(registry_path: Path, policy: dict) -> list[str]:
    env = smoke_git_environment(policy)
    selected = smoke_remote_names(policy)
    for remote in selected:
        completed = subprocess.run(
            ["git", "-C", str(registry_path), "push", remote, "HEAD:main"],
            check=False,
            env=env,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"failed to push smoke-test registry to remote {remote}")
    return selected


def remote_checkpoint_head(host: str, flake: str, leader: str) -> dict | None:
    command = (
        "PATH=/run/current-system/sw/bin:$PATH python3 - <<'PY'\n"
        "import json\n"
        "path = '/var/lib/cluster-identity/local-state/checkpoint.json'\n"
        f"leader = {leader!r}\n"
        "try:\n"
        "    with open(path, 'r', encoding='utf-8') as handle:\n"
        "        checkpoint = json.load(handle)\n"
        "except FileNotFoundError:\n"
        "    checkpoint = {}\n"
        "print(json.dumps((checkpoint.get('heads') or {}).get(leader)))\n"
        "PY"
    )
    completed = ssh_run(host, flake, command, capture_output=True)
    if completed.returncode != 0 or not completed.stdout:
        return None
    value = json.loads(completed.stdout.strip())
    return value if isinstance(value, dict) else None


def cmd_identity_smoke_test(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    inventory = transport.inventory(args.flake)
    verify_hosts = resolve_hosts_arg(
        args.verify_node or operator_hosts(inventory), inventory
    )
    try:
        published = snapshot.publish_snapshot(
            args.registry,
            _snapshot_path(policy, args.snapshot_dir),
            policy,
            leader,
            signing_key_path(policy, args.signing_key),
        )
        trigger_remote_fetch(verify_hosts, args.flake)
        deadline = time.time() + args.poll_seconds
        pending = set(verify_hosts)
        while pending and time.time() < deadline:
            for host in sorted(list(pending)):
                head = remote_checkpoint_head(host, args.flake, leader)
                if (
                    head
                    and head.get("cid") == published["rootCid"]
                    and head.get("rootSequence") == published["rootSequence"]
                ):
                    print(
                        f"{host}: accepted sequence {published['rootSequence']} {published['rootCid']}"
                    )
                    pending.remove(host)
            if pending:
                time.sleep(args.poll_interval)
        if pending:
            raise RuntimeError(
                "timed out waiting for IPNS convergence on: "
                + ", ".join(sorted(pending))
            )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        RuntimeError,
        ValueError,
    ) as error:
        print(error, file=sys.stderr)
        return 1
    print("IPFS/IPNS registry smoke test completed successfully")
    return 0


def cmd_bundle_emergency_publish(args) -> int:
    target_host, ssh_user = resolve_target(args.node, args.flake)
    bundles.publish_bundle(
        args.node,
        args.service,
        args.generation,
        args.source,
        args.target_path,
        target_host,
        ssh_user,
    )
    print(
        f"EMERGENCY plaintext install completed for {args.service} generation "
        f"{args.generation} on {args.node} via {target_host}"
    )
    return 0


def cmd_bundle_seal(args) -> int:
    policy = load_policy(args.policy)
    inventory = transport.inventory(args.flake)
    host_age = (
        ((inventory.get("identities") or {}).get("services") or {}).get("host-age")
        or {}
    ).get(args.node) or {}
    recipient = args.recipient or (((host_age.get("public") or {}).get("ageRecipient")))
    if not recipient:
        print(f"No host-age recipient found for {args.node}", file=sys.stderr)
        return 1
    expected_public = (
        public_from_inventory_data(inventory, args.node, args.service)
        if args.from_inventory
        else {}
    )
    leader = args.leader or socket.gethostname()
    try:
        manifest = bundles.seal_bundle(
            registry=args.registry,
            node=args.node,
            service=args.service,
            generation=args.generation,
            source=args.source,
            target_path=args.target_path,
            recipient_public_key=recipient,
            expected_public=expected_public,
            leader=leader,
            leader_key=args.leader_key or leader_key(policy, leader),
            signing_key=signing_key_path(policy, args.signing_key),
            cluster_id=registry.cluster_id(policy) or "",
        )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    commit(
        args.registry,
        f"bundle seal {args.node} {args.service} gen {args.generation}",
        not args.no_commit,
    )
    print(manifest)
    return 0


def cmd_receipt_write(args) -> int:
    policy = load_policy(args.policy)
    target = args.path or Path(
        f"/var/lib/cluster-identity/receipts/{args.node}-{args.service}-gen-{args.generation}.json"
    )
    event = find_event(args.registry, args.node, args.service, args.generation)
    if not event:
        print(
            f"No event found for {args.node}/{args.service} generation {args.generation}",
            file=sys.stderr,
        )
        return 1
    bundle_manifest = (event.get("privateDelivery") or {}).get("bundleManifest")
    if not bundle_manifest:
        print("The selected event has no private bundle manifest", file=sys.stderr)
        return 1
    receipt_signing_key = args.signing_key or Path(
        policy.get("receiptSigningKeyPath") or "/etc/ssh/ssh_host_ed25519_key"
    )
    try:
        bundles.write_receipt(
            target,
            args.node,
            args.service,
            args.generation,
            args.status,
            args.activated,
            args.signed_by_node,
            receipt_signing_key,
            args.signature,
            registry.cluster_id(policy) or "",
            event["eventId"],
            bundle_manifest,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    print(target)
    return 0


def cmd_receipt_collect(args) -> int:
    target_host, ssh_user = resolve_target(args.node, args.flake)
    destination = (
        args.registry
        / "receipts"
        / f"{args.node}-{args.service}-gen-{args.generation}.json"
    )
    bundles.collect_receipt(
        args.node, args.service, args.generation, target_host, ssh_user, destination
    )
    commit(
        args.registry,
        f"receipt collect {args.node} {args.service} gen {args.generation}",
        not args.no_commit,
    )
    print(destination)
    return 0


def publish_identity_ledger_after_deploy(args) -> int:
    if not getattr(args, "publish_identities", False) or args.dry_run:
        return 0
    publish_args = argparse.Namespace(
        registry=DEFAULT_REGISTRY,
        out=args.out,
        policy=DEFAULT_POLICY,
        no_reconcile=False,
        signature=None,
        signing_key=None,
    )
    command = [
        clusterctl_executable(),
        "--flake",
        args.flake,
        "identity",
        "publish",
        "--out",
        str(args.out),
        "--no-fetch",
        "--allow-cross-leader-publish",
    ]
    if identity_publish_requires_sudo(publish_args):
        privilege = Privilege.ROOT_LOCAL
    else:
        privilege = Privilege.USER
    print("\nPublishing the deploying leader's identity ledger:")
    print("  " + shlex.join(privileged_command(command, privilege)))
    return run_command(
        command,
        privilege=privilege,
        runner=subprocess.run,
        authorization_runner=subprocess.run,
    ).returncode


def cmd_update(args) -> int:
    root = flake_root(args.flake)
    before = update.top_level_locked(update.read_lock(root))

    command = ["nix", "flake", "update", "--flake", args.flake, *args.inputs]
    print("Running:")
    print("  " + " ".join(command))
    code = subprocess.run(command, check=False).returncode
    if code != 0:
        return code

    after = update.top_level_locked(update.read_lock(root))
    changes = update.diff_top_level(before, after)
    if not changes:
        print("\nNo input changes.")
        return 0

    print("\nInput changes:")
    for change in changes:
        print(f"  {change}")

    check_command = ["nix", "flake", "check", args.flake]
    print("\nRunning:")
    print("  " + " ".join(check_command))
    code = subprocess.run(check_command, check=False).returncode
    if code != 0:
        print("\nBuild check failed; leaving flake.lock uncommitted.")
        return code

    message = "Update flake inputs\n\n" + "\n".join(changes)
    subprocess.run(["git", "-C", str(root), "add", "flake.lock"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-m", message], check=True)
    print("\nCommitted flake.lock update.")

    print("\nSuggested next step:")
    print(f"  nix run {args.flake}#clusterctl -- deploy all --dry-run")
    return 0


def cmd_deploy(args) -> int:
    deploy_privilege = (
        Privilege.ROOT_LOCAL if args.local_root else Privilege.USER
    )
    if args.hosts == ["all"]:
        inventory = transport.inventory(args.flake)
        hosts = resolve_hosts_arg(args.hosts, inventory)
        colmena_hosts = []
        deploy_rs_hosts = []
        print("Fleet deployment safety routing:")
        for host in hosts:
            reasons = deploy.boot_risk_reasons(host, args.flake)
            if reasons:
                deploy_rs_hosts.append(host)
                print(f"  {host}: deploy-rs")
                for reason in reasons:
                    print(f"    - {reason}")
            else:
                colmena_hosts.append(host)
                print(f"  {host}: colmena (boot-critical state unchanged)")

        for host in deploy_rs_hosts:
            command = [
                "nix",
                "run",
                f"{args.flake}#deploy-rs",
                "--",
                "--skip-checks",
                f".#{host}",
            ]
            print("\nProtected deploy-rs route:")
            print("  " + " ".join(command))
            if not args.dry_run:
                code = run_command(
                    command,
                    privilege=deploy_privilege,
                    runner=subprocess.run,
                    authorization_runner=subprocess.run,
                ).returncode
                if code != 0:
                    return code

        if not colmena_hosts:
            return publish_identity_ledger_after_deploy(args)
        goal = "dry-activate" if args.dry_run else "switch"
        command = [
            "nix",
            "run",
            f"{args.flake}#colmena",
            "--",
            "apply",
            goal,
            "--on",
            ",".join(colmena_hosts),
        ]
        print("\nColmena route:")
        print("  " + " ".join(command))
        code = run_command(
            command,
            privilege=deploy_privilege,
            runner=subprocess.run,
            authorization_runner=subprocess.run,
        ).returncode
        if code != 0:
            return code
        return publish_identity_ledger_after_deploy(args)
    inventory = transport.inventory(args.flake)
    hosts = resolve_hosts_arg(args.hosts, inventory)
    for host in hosts:
        candidates = deploy.candidates(host, args.out, args.flake)
        print(f"Resolved deploy candidates for {host}:")
        for index, (label, target) in enumerate(candidates, 1):
            print(f"  {index}. {label}: {target}")
        selected = candidates[0] if candidates else ("plain host name", host)
        print("\nSelected:")
        print(f"  {selected[0]} {selected[1]}")
        command = [
            "nix",
            "run",
            f"{args.flake}#deploy-rs",
            "--",
            "--skip-checks",
            f".#{host}",
        ]
        print("\nPlanned:" if args.dry_run else "\nRunning:")
        print("  " + " ".join(command))
        if not args.dry_run:
            code = run_command(
                command,
                privilege=deploy_privilege,
                runner=subprocess.run,
                authorization_runner=subprocess.run,
            ).returncode
            if code != 0:
                return code
        if host != hosts[-1]:
            print("")
    return publish_identity_ledger_after_deploy(args)


def cmd_install(args) -> int:
    inventory = transport.inventory(args.flake)
    try:
        plan = install.resolve_plan(inventory, args.host)
        result = install.probe(plan)
        install.validate_probe(plan, result)
    except (install.InstallError, subprocess.CalledProcessError) as error:
        print(f"Install refused: {error}", file=sys.stderr)
        return 2

    print("Install preflight passed:")
    print(f"  inventory host: {plan['host']}")
    print(f"  target: {plan['sshUser']}@{plan['targetHost']}")
    print(f"  hardware: {result.get('sys_vendor')} {result.get('product_name')}")
    print(
        f"  disk: {plan['device']} "
        f"({result.get('disk_size')} bytes, {result.get('disk_model')})"
    )
    command = install.command(plan, args.flake)
    print("\nPlanned:" if args.dry_run else "\nRunning:")
    print("  " + shlex.join(command))
    if args.dry_run:
        return 0
    if args.confirm != plan["installationId"]:
        print(
            "Install refused: --confirm must exactly match installationId "
            f"{plan['installationId']!r}",
            file=sys.stderr,
        )
        return 2
    return subprocess.run(command, check=False).returncode


def cmd_host_age_bootstrap(args) -> int:
    target_host, ssh_user = resolve_target(args.host, args.flake)
    private_key_path = args.target_path
    generate = (
        f"(command -v age-keygen >/dev/null 2>&1 && age-keygen -o {private_key_path} "
        f"|| nix shell nixpkgs#age -c age-keygen -o {private_key_path})"
    )
    if args.source:
        remote_tmp = f"/tmp/cluster-identity-host-age-{args.host}.agekey"
        subprocess.run(
            ["scp", str(args.source), f"{ssh_user}@{target_host}:{remote_tmp}"],
            check=True,
        )
        command = (
            "install -d -m 0700 /var/lib/cluster-identity/age "
            f"&& install -m 0400 -o root -g root {remote_tmp} {private_key_path} "
            f"&& rm -f {remote_tmp}"
        )
    else:
        command = (
            "install -d -m 0700 /var/lib/cluster-identity/age "
            f"&& test -s {private_key_path} || {generate} "
            f"&& chmod 0400 {private_key_path}"
        )
    subprocess.run(["ssh", f"{ssh_user}@{target_host}", command], check=True)
    public = subprocess.run(
        [
            "ssh",
            f"{ssh_user}@{target_host}",
            f"sed -n 's/^# public key: //p' {private_key_path}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    print(f"{args.host} {public}")
    return 0


def cmd_host_age_public(args) -> int:
    target_host, ssh_user = resolve_target(args.host, args.flake)
    completed = subprocess.run(
        [
            "ssh",
            f"{ssh_user}@{target_host}",
            f"sed -n 's/^# public key: //p' {args.target_path}",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    print(completed.stdout.strip())
    return 0


def cmd_host_age_rotate(args) -> int:
    public, backup = rotate_host_age_key(args.host, args.flake, args.target_path)
    print(f"{args.host} {public}")
    print(f"old key moved to {backup}")
    return 0


def add_registry_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)


def add_signing_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--signing-key", type=Path)
    parser.add_argument("--signature")


def build_parser(prog: str = "clusterctl") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--flake", default=os.environ.get("CLUSTERCTL_FLAKE", "."))
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("registry", help="inspect and operate the identity registry")
    reg_sub = reg.add_subparsers(dest="registry_command", required=True)
    for name, func in [
        ("ensure-v1", cmd_registry_ensure_v1),
        ("validate", cmd_registry_validate),
        ("reconcile", cmd_registry_reconcile),
        ("fetch-ipfs", cmd_registry_fetch_ipfs),
        ("listen-pubsub", cmd_registry_listen_pubsub),
        ("notify", cmd_registry_notify),
        ("status", cmd_registry_status),
    ]:
        labels = {
            "ensure-v1": "INTERNAL: initialize or migrate the activation-owned v1 registry",
            "fetch-ipfs": "INTERNAL: fetch, verify, and materialize trusted IPNS heads",
            "listen-pubsub": "INTERNAL: verify PubSub hints and trigger the normal fetch path",
            "reconcile": "EMERGENCY REPAIR: verify and rebuild materialized registry state",
        }
        p = reg_sub.add_parser(name, help=labels.get(name))
        add_registry_common(p)
        p.set_defaults(func=func)
    reg_sub.choices["ensure-v1"].add_argument("--no-commit", action="store_true")
    reg_sub.choices["notify"].add_argument("--target", action="append", default=[])
    reg_sub.choices["status"].add_argument("--node")
    reg_sub.choices["fetch-ipfs"].add_argument("--cache-dir", type=Path)
    reg_sub.choices["fetch-ipfs"].add_argument("--accepted-registry", type=Path)
    reg_sub.choices["listen-pubsub"].add_argument(
        "--trigger-unit",
        default="cluster-identity-fetch.service",
    )
    snapshot_parser = reg_sub.add_parser(
        "snapshot", help="INTERNAL: build a signed immutable snapshot"
    )
    add_registry_common(snapshot_parser)
    snapshot_parser.add_argument("--snapshot-dir", type=Path)
    snapshot_parser.add_argument("--publisher")
    snapshot_parser.add_argument("--signing-key", type=Path)
    snapshot_parser.set_defaults(func=cmd_registry_snapshot)
    publish_ipfs = reg_sub.add_parser(
        "publish-ipfs", help="INTERNAL: publish a snapshot through IPFS/IPNS"
    )
    add_registry_common(publish_ipfs)
    publish_ipfs.add_argument("--snapshot-dir", type=Path)
    publish_ipfs.add_argument("--publisher")
    publish_ipfs.add_argument("--signing-key", type=Path)
    publish_ipfs.set_defaults(func=cmd_registry_publish_ipfs)
    publish_status = reg_sub.add_parser(
        "publish-status",
        help="INTERNAL: publish this node's materialized identity status through IPNS",
    )
    add_registry_common(publish_status)
    publish_status.add_argument("--status-dir", type=Path)
    publish_status.add_argument("--node")
    publish_status.add_argument("--key-name")
    publish_status.add_argument("--expected-name")
    publish_status.add_argument("--signing-key", type=Path)
    publish_status.set_defaults(func=cmd_registry_publish_status)
    ipns_key = reg_sub.add_parser(
        "ipns-key", help="INTERNAL: manage activation-owned IPNS keys"
    )
    ipns_key_sub = ipns_key.add_subparsers(dest="ipns_key_command", required=True)
    ipns_key_ensure = ipns_key_sub.add_parser("ensure")
    ipns_key_ensure.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    ipns_key_ensure.add_argument("--publisher")
    ipns_key_ensure.add_argument("--key-name")
    ipns_key_ensure.add_argument("--key-file", type=Path, required=True)
    ipns_key_ensure.add_argument("--expected-name")
    ipns_key_ensure.set_defaults(func=cmd_registry_ipns_key_ensure)
    status_ipns_key = reg_sub.add_parser(
        "status-ipns-key", help="INTERNAL: manage node-local status IPNS keys"
    )
    status_ipns_key_sub = status_ipns_key.add_subparsers(
        dest="status_ipns_key_command",
        required=True,
    )
    status_ipns_key_ensure = status_ipns_key_sub.add_parser("ensure")
    status_ipns_key_ensure.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    status_ipns_key_ensure.add_argument("--node")
    status_ipns_key_ensure.add_argument("--key-name")
    status_ipns_key_ensure.add_argument("--key-file", type=Path)
    status_ipns_key_ensure.add_argument("--expected-name")
    status_ipns_key_ensure.set_defaults(func=cmd_registry_status_ipns_key_ensure)
    ident = sub.add_parser("identity")
    ident_sub = ident.add_subparsers(dest="identity_command", required=True)
    publish_all = ident_sub.add_parser("publish")
    add_registry_common(publish_all)
    publish_all.add_argument("--service", action="append", default=[])
    publish_all.add_argument("--node", action="append", default=[])
    publish_all.add_argument("--generation", type=int)
    publish_all.add_argument("--state", choices=sorted(VALID_STATES))
    publish_all.add_argument("--leader")
    publish_all.add_argument("--leader-key")
    add_signing_common(publish_all)
    publish_all.add_argument("--allow-duplicate", action="store_true")
    publish_all.add_argument("--allow-cross-leader-publish", action="store_true")
    publish_all.add_argument(
        "--burn-stale",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="burn stale same-leader live identity claims that are absent from or older than current inventory",
    )
    publish_all.add_argument(
        "--burn-guarded-stale",
        action="store_true",
        help="also burn stale guarded services such as host-age, ssh-host, and IPNS identities",
    )
    publish_all.add_argument("--no-commit", action="store_true")
    publish_all.add_argument("--no-reconcile", action="store_true")
    publish_all.add_argument(
        "--fetch", action=argparse.BooleanOptionalAction, default=True
    )
    publish_all.add_argument(
        "--push", action=argparse.BooleanOptionalAction, default=True
    )
    publish_all.add_argument("--remote", action="append")
    publish_all.add_argument("--notify", action="store_true")
    publish_all.set_defaults(func=cmd_identity_publish)

    promote = ident_sub.add_parser("promote")
    add_registry_common(promote)
    promote.add_argument("node")
    promote.add_argument("service")
    promote.add_argument("--generation", type=int, required=True)
    promote.add_argument("--leader")
    promote.add_argument("--leader-key")
    add_signing_common(promote)
    promote.add_argument("--no-commit", action="store_true")
    promote.set_defaults(func=cmd_identity_promote)

    resolve = ident_sub.add_parser("resolve")
    add_registry_common(resolve)
    resolve.add_argument("--winner-event", required=True)
    resolve.add_argument("--loser-event", required=True)
    resolve.add_argument("--reason", required=True)
    resolve.add_argument("--observed-root-cid")
    resolve.add_argument("--leader")
    resolve.add_argument("--leader-key")
    resolve.add_argument("--signing-key", type=Path)
    resolve.add_argument("--no-commit", action="store_true")
    resolve.add_argument(
        "--push", action=argparse.BooleanOptionalAction, default=True
    )
    resolve.set_defaults(func=cmd_identity_resolve)

    burn = ident_sub.add_parser("burn")
    add_registry_common(burn)
    burn.add_argument("node")
    burn.add_argument("service")
    burn.add_argument("--generation", type=int, required=True)
    burn.add_argument("--fingerprint", required=True)
    burn.add_argument("--reason", required=True)
    burn.add_argument("--leader")
    burn.add_argument("--leader-key")
    add_signing_common(burn)
    burn.add_argument("--no-commit", action="store_true")
    burn.set_defaults(func=cmd_identity_burn)

    rotate = ident_sub.add_parser("rotate")
    add_registry_common(rotate)
    rotate.add_argument("node")
    rotate.add_argument("service")
    rotate.add_argument("--generation", type=int)
    rotate.add_argument("--allow-missing", action="store_true")
    rotate.add_argument("--dry-run", action="store_true")
    rotate.add_argument(
        "--sops-age-key-file",
        type=Path,
        default=Path(os.environ.get("SOPS_AGE_KEY_FILE", DEFAULT_HOST_AGE_TARGET_PATH)),
    )
    rotate.add_argument(
        "--publish", action=argparse.BooleanOptionalAction, default=True
    )
    rotate.add_argument(
        "--publish-push", action=argparse.BooleanOptionalAction, default=True
    )
    rotate.add_argument(
        "--burn-stale",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="burn stale same-leader live identity claims after publishing the rotated inventory record",
    )
    rotate.add_argument(
        "--burn-guarded-stale",
        action="store_true",
        help="also burn stale guarded services such as host-age, ssh-host, and IPNS identities",
    )
    rotate.add_argument("--notify", action="store_true")
    rotate.add_argument("--no-reconcile", action="store_true")
    rotate.add_argument("--leader")
    rotate.add_argument("--leader-key")
    add_signing_common(rotate)
    rotate.add_argument("--no-commit", action="store_true")
    rotate.set_defaults(func=cmd_identity_rotate)

    matrix = ident_sub.add_parser("matrix")
    matrix.add_argument("--node", action="append", default=[])
    matrix.add_argument("--service", action="append", default=[])
    matrix.add_argument("--out", type=Path, default=DEFAULT_OUT)
    matrix.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    matrix.add_argument("--no-live", action="store_true")
    matrix.add_argument(
        "--fetch", action=argparse.BooleanOptionalAction, default=True
    )
    matrix.add_argument(
        "--burn-limit",
        type=int,
        default=None,
        help="maximum burned records to show per live matrix cell; negative means unlimited",
    )
    matrix.add_argument(
        "--status-ack",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="fetch signed node status IPNS records and annotate active/acknowledged states",
    )
    matrix.add_argument("--status-cache", type=Path, default=DEFAULT_STATUS_CACHE)
    matrix.add_argument("--only-missing", action="store_true")
    matrix.add_argument("--json", action="store_true")
    matrix.set_defaults(func=cmd_identity_matrix)

    generate_missing = ident_sub.add_parser("generate-missing")
    add_registry_common(generate_missing)
    generate_missing.add_argument("--node", action="append", default=[])
    generate_missing.add_argument("--service", action="append", default=[])
    generate_missing.add_argument(
        "--all",
        action="store_true",
        help="generate every missing identity from inventory; this is the default when no --node is supplied",
    )
    generate_missing.add_argument("--dry-run", action="store_true")
    generate_missing.add_argument(
        "--sops-age-key-file",
        type=Path,
        default=Path(os.environ.get("SOPS_AGE_KEY_FILE", DEFAULT_HOST_AGE_TARGET_PATH)),
    )
    generate_missing.add_argument(
        "--publish", action=argparse.BooleanOptionalAction, default=True
    )
    generate_missing.add_argument(
        "--publish-push", action=argparse.BooleanOptionalAction, default=True
    )
    generate_missing.add_argument("--notify", action="store_true")
    generate_missing.add_argument("--no-reconcile", action="store_true")
    generate_missing.add_argument("--leader")
    generate_missing.add_argument("--leader-key")
    add_signing_common(generate_missing)
    generate_missing.add_argument("--no-commit", action="store_true")
    generate_missing.set_defaults(func=cmd_identity_generate_missing)

    smoke = ident_sub.add_parser("smoke-test")
    add_registry_common(smoke)
    smoke.add_argument("--verify-node", action="append", default=[])
    smoke.add_argument("--poll-seconds", type=int, default=90)
    smoke.add_argument("--poll-interval", type=float, default=2.0)
    smoke.add_argument("--snapshot-dir", type=Path)
    smoke.add_argument("--leader")
    smoke.add_argument("--signing-key", type=Path)
    smoke.set_defaults(func=cmd_identity_smoke_test)

    bundle = sub.add_parser("bundle")
    bundle_sub = bundle.add_subparsers(dest="bundle_command", required=True)
    publish_bundle = bundle_sub.add_parser(
        "emergency-publish",
        help="EMERGENCY REPAIR: install plaintext private material over SSH",
    )
    publish_bundle.add_argument("node")
    publish_bundle.add_argument("service")
    publish_bundle.add_argument("--generation", type=int, required=True)
    publish_bundle.add_argument("--source", type=Path, required=True)
    publish_bundle.add_argument("--target-path", required=True)
    publish_bundle.set_defaults(func=cmd_bundle_emergency_publish)
    seal_bundle = bundle_sub.add_parser("seal")
    add_registry_common(seal_bundle)
    seal_bundle.add_argument("node")
    seal_bundle.add_argument("service")
    seal_bundle.add_argument("--generation", type=int, required=True)
    seal_bundle.add_argument("--source", type=Path, required=True)
    seal_bundle.add_argument("--target-path", required=True)
    seal_bundle.add_argument("--recipient")
    seal_bundle.add_argument("--from-inventory", action="store_true")
    seal_bundle.add_argument("--leader")
    seal_bundle.add_argument("--leader-key")
    add_signing_common(seal_bundle)
    seal_bundle.add_argument("--no-commit", action="store_true")
    seal_bundle.set_defaults(func=cmd_bundle_seal)

    receipt = sub.add_parser("receipt")
    receipt_sub = receipt.add_subparsers(dest="receipt_command", required=True)
    write = receipt_sub.add_parser("write")
    write.add_argument("--node", required=True)
    write.add_argument("--service", required=True)
    write.add_argument("--generation", type=int, required=True)
    write.add_argument("--status", default="node-activated")
    write.add_argument("--activated", action="store_true", default=True)
    write.add_argument("--signed-by-node")
    add_registry_common(write)
    add_signing_common(write)
    write.add_argument("--path", type=Path)
    write.set_defaults(func=cmd_receipt_write)
    collect = receipt_sub.add_parser("collect")
    collect.add_argument("node")
    collect.add_argument("service")
    collect.add_argument("--generation", type=int, required=True)
    collect.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    collect.add_argument("--no-commit", action="store_true")
    collect.set_defaults(func=cmd_receipt_collect)

    deploy_p = sub.add_parser("deploy")
    deploy_p.add_argument(
        "hosts",
        nargs="+",
        help="host names to deploy with deploy-rs, or 'all' to deploy every host through colmena",
    )
    deploy_p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    deploy_p.add_argument("--dry-run", action="store_true")
    deploy_p.add_argument(
        "--local-root",
        action="store_true",
        help="run the local deploy-rs process as root for an explicitly root-owned SSH identity",
    )
    deploy_p.add_argument(
        "--publish-identities",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="publish the deploying leader's flake identity ledger after a successful deploy",
    )
    deploy_p.set_defaults(func=cmd_deploy)

    update_p = sub.add_parser(
        "update",
        help="update flake inputs, verify with a build check, and commit flake.lock",
    )
    update_p.add_argument(
        "inputs",
        nargs="*",
        help="specific input names to update; omit to update every input",
    )
    update_p.set_defaults(func=cmd_update)

    install_p = sub.add_parser(
        "install",
        help="install an explicitly allowlisted bare-metal host with nixos-anywhere",
    )
    install_p.add_argument("host")
    install_p.add_argument(
        "--confirm",
        help="required destructive confirmation; must match the inventory installationId",
    )
    install_p.add_argument(
        "--dry-run",
        action="store_true",
        help="run all remote safety checks and print the command without installing",
    )
    install_p.set_defaults(func=cmd_install)

    host_age = sub.add_parser("host-age")
    host_age_sub = host_age.add_subparsers(dest="host_age_command", required=True)
    bootstrap = host_age_sub.add_parser("bootstrap")
    bootstrap.add_argument("host")
    bootstrap.add_argument("--source", type=Path)
    bootstrap.add_argument(
        "--target-path", default="/var/lib/cluster-identity/age/host.agekey"
    )
    bootstrap.set_defaults(func=cmd_host_age_bootstrap)
    public = host_age_sub.add_parser("public")
    public.add_argument("host")
    public.add_argument(
        "--target-path", default="/var/lib/cluster-identity/age/host.agekey"
    )
    public.set_defaults(func=cmd_host_age_public)
    rotate = host_age_sub.add_parser(
        "rotate",
        help="EMERGENCY REPAIR: replace a host-age key and retain the old key",
    )
    rotate.add_argument("host")
    rotate.add_argument(
        "--target-path", default="/var/lib/cluster-identity/age/host.agekey"
    )
    rotate.set_defaults(func=cmd_host_age_rotate)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        mode = execution_mode()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    program = {
        ExecutionMode.OPERATE: "clusterctl",
        ExecutionMode.CHECK: "clusterchk",
        ExecutionMode.PLAN: "clusterplan",
    }[mode]
    parser = build_parser(program)
    args = parser.parse_args(argv)
    try:
        prepare_invocation(args, mode)
    except ValueError as error:
        parser.error(str(error))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
