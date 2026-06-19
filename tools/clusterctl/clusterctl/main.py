import argparse
import hashlib
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import bundles, deploy, materialize, notify, registry, transport
from .events import VALID_STATES, new_event_id, now_utc, read_json, write_json
from .signing import sign_record

DEFAULT_REGISTRY = Path("/var/lib/cluster-identity/registry")
DEFAULT_OUT = Path("/run/cluster-identity")
DEFAULT_POLICY = Path("/etc/cluster-identity/policy.json")
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
    "ssh-host",
    "yggdrasil",
    "radicle",
    "git-annex",
]

STATE_ABBREVIATIONS = {
    "planned": "p",
    "staged": "s",
    "private-delivered": "pd",
    "node-received": "nr",
    "node-activated": "na",
    "leader-verified": "lv",
    "active": "a",
    "deprecated": "d",
    "removed": "rm",
    "burned": "b",
}

IDENTITY_SOURCE_FILES = {
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
    configured = rules.get("signingKeyPath") or policy.get("signingKeyPath")
    if configured:
        return Path(configured)
    raise ValueError("no signing key configured; pass --signing-key or set policy.signingKeyPath")


def attach_signature(record: dict, key_path: Path | None, provided: str | None, policy: dict) -> dict:
    if provided:
        record["signature"] = provided
        return record
    path = signing_key_path(policy, key_path)
    if not path.exists():
        raise ValueError(f"signing key does not exist: {path}")
    record["signature"] = sign_record(record, path)
    return record


def commit(registry_path: Path, message: str, enabled: bool = True) -> None:
    if enabled:
        transport.git_commit_if_possible(registry_path, message)


def cmd_registry_init(args) -> int:
    registry.init_registry(args.registry)
    commit(args.registry, "identity registry init", not args.no_commit)
    print(f"Initialized registry at {args.registry}")
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


def cmd_registry_materialize(args) -> int:
    materialize.materialize_state(args.registry, args.out)
    print(f"Materialized state into {args.out}")
    return 0


def cmd_registry_sync(args) -> int:
    policy = load_policy(args.policy)
    ensure_registry_git_repo(args.registry)
    if args.sync_remotes:
        transport.sync_git_remotes(args.registry, ((policy.get("registry") or {}).get("remotes") or {}), args.prune_remotes)
    registry.sync(args.registry, args.out, policy)
    print(f"Synced and materialized {args.registry} into {args.out}")
    return 0


def cmd_registry_push(args) -> int:
    policy = load_policy(args.policy)
    ensure_registry_git_repo(args.registry)
    if args.sync_remotes:
        transport.sync_git_remotes(args.registry, ((policy.get("registry") or {}).get("remotes") or {}), args.prune_remotes)
    remotes = args.remote or transport.policy_remotes(policy, "push") or transport.git_remotes(args.registry)
    if not remotes:
        print(f"No Git remotes configured in {args.registry}")
        return 0
    for remote in remotes:
        print(f"Pushing {remote}")
    transport.git_push_remotes(args.registry, remotes, policy)
    return 0


def cmd_registry_remotes_sync(args) -> int:
    policy = load_policy(args.policy)
    ensure_registry_git_repo(args.registry)
    changed = transport.sync_git_remotes(args.registry, ((policy.get("registry") or {}).get("remotes") or {}), args.prune)
    if changed:
        for item in changed:
            print(item)
    else:
        print("Registry remotes already match policy")
    return 0


def cmd_registry_notify(args) -> int:
    targets = args.target
    if not targets:
        bootstrap = transport.host_bootstrap(args.flake)
        targets = sorted(bootstrap.keys())
    notify.notify_targets(targets, args.out, args.flake)
    print(f"Notification attempted for: {', '.join(targets)}")
    return 0


def cmd_registry_status(args) -> int:
    print(f"Registry: {args.registry}")
    print(f"Materialized: {args.out}")
    for name in ["active.json", "staged.json", "deprecated.json", "burned.json"]:
        state = read_json(args.out / name, None)
        if state is None:
            state = read_json(args.registry / "state" / name, None)
        count = 0
        if isinstance(state, dict):
            count = sum(len(services) for services in (state.get("nodes") or {}).values())
        print(f"{name}: {count} records")
    return 0


def event_path(registry_path: Path, event_id: str) -> Path:
    return registry_path / "events" / f"{event_id}.json"


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
        "sourceTimestamp": record.get("sourceTimestamp") or record.get("keyGeneratedAt"),
        "requiresReceipt": bool(private.get("requiresReceipt", False)),
    }
    return {key: value for key, value in delivery.items() if value is not None}


def flake_identity_records(inventory: dict, services: set[str] | None = None, nodes: set[str] | None = None):
    identity_services = (((inventory.get("identities") or {}).get("services") or {}))
    for service in sorted(identity_services.keys()):
        if services and service not in services:
            continue
        service_records = identity_services.get(service) or {}
        for node in sorted(service_records.keys()):
            if nodes and node not in nodes:
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


def inventory_hosts(inventory: dict, nodes: set[str] | None = None) -> list[tuple[str, dict]]:
    hosts = (inventory.get("hosts") or {})
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


def desired_identity_services_for_host(host: dict) -> set[str]:
    dendrites = set(host.get("dendrites") or [])
    networks = set(host.get("networks") or [])
    org = host.get("org") or {}
    cluster_identity = ((org.get("clusterIdentity")) or {})
    radicle_org = (((org.get("network") or {}).get("radicle")) or {})
    service_flags = cluster_identity.get("services") or {}

    desired: set[str] = set()

    if "system/cluster-identity" in dendrites or cluster_identity.get("role"):
        desired.add("host-age")

    ssh_cfg = service_flags.get("ssh") or {}
    if ssh_cfg.get("enableLiveKnownHosts") or ssh_cfg.get("enableLiveIdentity"):
        desired.add("ssh-host")

    ygg_cfg = service_flags.get("yggdrasil") or {}
    if ygg_cfg.get("enableLiveIdentity") or "privateYggdrasil" in networks:
        desired.add("yggdrasil")

    radicle_cfg = service_flags.get("radicle") or {}
    radicle_live = radicle_cfg.get("enableLiveIdentity")
    if radicle_live is not False and (radicle_live or "network/radicle" in dendrites or radicle_org.get("seed")):
        desired.add("radicle")

    annex_cfg = service_flags.get("gitAnnex") or {}
    annex_live = annex_cfg.get("enableLiveIdentity")
    if annex_live is not False and (annex_live or "storage/git-annex" in dendrites):
        desired.add("git-annex")

    return desired


def identity_record_cell(record: dict) -> str:
    generation = record.get("generation")
    generation_text = generation if isinstance(generation, int) else "?"
    state = record.get("state") or "unknown"
    state_text = STATE_ABBREVIATIONS.get(state, state[:2])
    return f"g{generation_text}/{state_text}"


def ssh_target_prefix(node: str, bootstrap_entry: dict) -> list[str]:
    target_host = bootstrap_entry.get("targetHost") or node
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
    return IDENTITY_SOURCE_FILES.get(service, "inventory/identities.nix")


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
            lines.append(f'{space}  {json.dumps(str(key))} = {rendered};')
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
        raise ValueError(f"no writable source ledger is configured for service {service!r}")
    return flake_root(flake) / relative


def ssh_completed(node: str, flake: str, remote_command: str, *, input_text: str | None = None) -> subprocess.CompletedProcess:
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


def capture_host_age_public(node: str, flake: str, target_path: str = DEFAULT_HOST_AGE_TARGET_PATH) -> str:
    target_host, ssh_user = resolve_target(node, flake)
    completed = subprocess.run(
        ["ssh", f"{ssh_user}@{target_host}", f"sed -n 's/^# public key: //p' {target_path}"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return completed.stdout.strip()


def ensure_host_age_key(node: str, flake: str, target_path: str = DEFAULT_HOST_AGE_TARGET_PATH) -> str:
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


def capture_yggdrasil_public(node: str, flake: str) -> dict:
    completed = ssh_completed(node, flake, "", input_text=YGGDRASIL_DISCOVERY_SCRIPT)
    return json.loads(completed.stdout)


def capture_ssh_host_key(node: str, flake: str) -> str:
    completed = ssh_completed(node, flake, "cat /etc/ssh/ssh_host_ed25519_key.pub")
    return completed.stdout.strip()


def capture_radicle_node_id(node: str, flake: str) -> str:
    completed = ssh_completed(node, flake, "sudo -u radicle env RAD_HOME=/var/lib/radicle sh -lc \"rad self --did | sed 's/^did:key://'\"")
    return completed.stdout.strip()


def host_age_recipients_path(flake: str) -> Path:
    return flake_root(flake) / "inventory/keys/host-age-recipients.nix"


def update_host_age_recipient_file(flake: str, node: str, public_key: str) -> None:
    path = host_age_recipients_path(flake)
    recipients = nix_file_json(path)
    recipients[node] = {
        "publicKey": public_key,
        "keyType": "age-x25519",
        "privateKeyPath": DEFAULT_HOST_AGE_TARGET_PATH,
        "enrolledAt": now_utc(),
        "enrollment": "root-ssh",
    }
    write_nix_value(path, recipients)


def update_identity_source_file(flake: str, service: str, node: str, record: dict) -> None:
    path = identity_source_path(flake, service)
    records = nix_file_json(path)
    records[node] = record
    write_nix_value(path, records)


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
    raise ValueError(f"automatic generation is not implemented for service {service!r}")


def derive_git_annex_payload(inventory: dict, node: str) -> dict:
    ygg_node = (((inventory.get("networks") or {}).get("privateYggdrasil") or {}).get("nodes") or {}).get(node) or {}
    aliases = ygg_node.get("aliases") or []
    host_alias = aliases[0] if aliases else f"{node}-ygg"
    repo_root = ((((inventory.get("storageFabric") or {}).get("annex")) or {}).get("repoRoot")) or "/srv/annex/cluster-data"
    host = (inventory.get("hosts") or {}).get(node) or {}
    group = ((((host.get("org") or {}).get("storage")) or {}).get("annex") or {}).get("group")
    ssh_public_key = ((((host.get("org") or {}).get("storage")) or {}).get("annex") or {}).get("sshPublicKey")
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


def cmd_registry_resign_placeholders(args) -> int:
    policy = load_policy(args.policy)
    changed = 0

    for _path, event in registry.load_events(args.registry):
        signature = (event.get("signature") or "").strip()
        if not signature.startswith("placeholder-signature:"):
            continue
        attach_signature(event, args.signing_key, args.signature, policy)
        write_json(_path, event)
        changed += 1

    for _path, receipt in registry.load_receipts(args.registry):
        signature = (receipt.get("signature") or "").strip()
        if not signature.startswith("placeholder-signature:"):
            continue
        attach_signature(receipt, args.signing_key, args.signature, policy)
        write_json(_path, receipt)
        changed += 1

    for _path, manifest in registry.load_bundle_manifests(args.registry):
        signature = (manifest.get("signature") or "").strip()
        if not signature.startswith("placeholder-signature:"):
            continue
        attach_signature(manifest, args.signing_key, args.signature, policy)
        write_json(_path, manifest)
        changed += 1

    failures = registry.validate_registry(args.registry, policy)
    if failures:
        print("Registry validation failed after re-signing:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    if changed:
        commit(args.registry, "registry re-sign placeholder signatures", not args.no_commit)
    print(f"Re-signed {changed} placeholder record(s)")
    return 0


def build_identity_matrix(inventory: dict, services: set[str] | None = None, nodes: set[str] | None = None) -> dict:
    hosts = inventory_hosts(inventory, nodes)
    identities = (((inventory.get("identities") or {}).get("services")) or {})
    desired_by_node = {node: desired_identity_services_for_host(host) for node, host in hosts}

    service_names = set()
    for desired in desired_by_node.values():
        service_names.update(desired)
    for service_name, service_records in identities.items():
        for node in service_records.keys():
            if nodes and node not in nodes:
                continue
            service_names.add(service_name)

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
            if desired and record:
                cell = identity_record_cell(record)
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
                        "sourceLedger": source_ledger_for_service(service_name),
                    }
                )
            elif record:
                cell = f"extra {identity_record_cell(record)}"
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
                "record": record,
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
        "missing": missing,
        "extra": extra,
        "legend": {
            "-": "not desired on this host",
            "missing": "desired by inventory metadata but absent from the flake identity source ledger",
            "gN/x": "present in the flake identity source ledger at generation N, state x",
            "extra gN/x": "present in the flake identity source ledger but no longer implied by current inventory metadata",
        },
    }


def next_record_generation(record: dict | None) -> int:
    if not record:
        return 1
    generation = record.get("generation")
    if isinstance(generation, int):
        return generation + 1
    return 1


def identity_guidance(node: str, service: str, record: dict | None, bootstrap_entry: dict) -> list[str]:
    commands: list[str] = []
    publish_command = f"clusterctl identity publish --node {shlex.quote(node)} --service {shlex.quote(service)}"
    generate_command = f"clusterctl identity generate-missing --node {shlex.quote(node)} --service {shlex.quote(service)}"
    ssh_prefix = shlex.join(ssh_target_prefix(node, bootstrap_entry))
    generation = next_record_generation(record)

    if service == "host-age":
        if record is None:
            commands.append(generate_command)
        if record:
            commands.append(f"clusterctl host-age rotate {shlex.quote(node)}")
            commands.append(f"clusterctl host-age public {shlex.quote(node)}")
        else:
            commands.append(f"clusterctl host-age bootstrap {shlex.quote(node)}")
            commands.append(f"clusterctl host-age public {shlex.quote(node)}")
        commands.append("# update inventory/keys/host-age-recipients.nix with the printed public recipient")
        commands.append(publish_command)
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
        commands.append("# if you rotated the host key first, bump generation and update inventory/identity-services/yggdrasil.nix")
        commands.append(publish_command)
        if record and (record.get("private") or {}).get("targetPath"):
            target_path = (record.get("private") or {}).get("targetPath")
            commands.append(
                f"clusterctl bundle seal {shlex.quote(node)} yggdrasil --generation {generation} --source ./private/{node}-yggdrasil.key --target-path {shlex.quote(target_path)} --from-inventory"
            )
            commands.append(f"clusterctl receipt collect {shlex.quote(node)} yggdrasil --generation {generation}")
            commands.append(f"clusterctl identity promote {shlex.quote(node)} yggdrasil --generation {generation}")
        return commands

    if service == "ssh-host":
        if record is None:
            commands.append(generate_command)
        commands.append(f"{ssh_prefix} 'cat /etc/ssh/ssh_host_ed25519_key.pub'")
        commands.append("# update inventory/identity-services/ssh-host.nix with the current public host key")
        commands.append(publish_command)
        return commands

    if service == "radicle":
        if record is None:
            commands.append(generate_command)
        commands.append(f"{ssh_prefix} \"sudo -u radicle env RAD_HOME=/var/lib/radicle sh -lc \\\"rad self --did | sed 's/^did:key://'\\\"\"")
        commands.append("# update inventory/identity-services/radicle.nix with the current public node id")
        commands.append(publish_command)
        return commands

    if service == "git-annex":
        if record is None:
            commands.append(generate_command)
        commands.append("# record the host's git-annex endpoint metadata in inventory/identity-services/git-annex.nix")
        commands.append(publish_command)
        return commands

    commands.append(publish_command)
    return commands


def cmd_identity_matrix(args) -> int:
    inventory = transport.inventory(args.flake)
    services = normalize_filter_values(args.service)
    nodes = normalize_filter_values(args.node)
    report = build_identity_matrix(inventory, services, nodes)

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
        rows.append([row["service"], *[row["nodes"][node]["cell"] for node in report["hosts"]]])

    print("Desired identity matrix (services x hosts)")
    if rows:
        print(render_table(headers, rows))
    else:
        print("No identity rows matched the current filters.")

    print("\nLegend:")
    print("  -: not desired on this host")
    print("  missing: desired by inventory metadata but absent from the flake identity source ledger")
    print("  gN/x: present with generation N and state x (a=active, s=staged, d=deprecated, b=burned)")
    print("  extra gN/x: present in the ledger but not implied by current inventory metadata")

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
            for command in identity_guidance(node, service_name, record, bootstrap.get(node) or {}):
                print(command)

    return 0


def cmd_identity_generate_missing(args) -> int:
    inventory = transport.inventory(args.flake)
    services = normalize_filter_values(args.service)
    nodes = normalize_filter_values(args.node)
    report = build_identity_matrix(inventory, services, nodes)
    missing = report["missing"]

    if not missing:
        print("No desired identities are missing.")
        return 0

    generated: list[tuple[str, str]] = []
    unsupported: list[tuple[str, str]] = []

    for item in missing:
        node = item["node"]
        service = item["service"]
        if service == "host-age":
            if args.dry_run:
                print(f"Would bootstrap host-age for {node} -> {source_ledger_for_service(service)}")
            else:
                public_key = ensure_host_age_key(node, args.flake)
                update_host_age_recipient_file(args.flake, node, public_key)
                print(f"Generated host-age recipient for {node}")
            generated.append((node, service))
            continue

        if service == "yggdrasil":
            if args.dry_run:
                print(f"Would discover Yggdrasil identity for {node} -> {source_ledger_for_service(service)}")
            else:
                payload = capture_yggdrasil_public(node, args.flake)
                update_identity_source_file(args.flake, service, node, generated_identity_record(service, node, payload))
                print(f"Generated Yggdrasil public identity for {node}")
            generated.append((node, service))
            continue

        if service == "ssh-host":
            if args.dry_run:
                print(f"Would capture SSH host key for {node} -> {source_ledger_for_service(service)}")
            else:
                payload = {"sshHostKey": capture_ssh_host_key(node, args.flake)}
                update_identity_source_file(args.flake, service, node, generated_identity_record(service, node, payload))
                print(f"Captured SSH host key for {node}")
            generated.append((node, service))
            continue

        if service == "radicle":
            if args.dry_run:
                print(f"Would capture Radicle node id for {node} -> {source_ledger_for_service(service)}")
            else:
                payload = {"radicleNodeId": capture_radicle_node_id(node, args.flake)}
                update_identity_source_file(args.flake, service, node, generated_identity_record(service, node, payload))
                print(f"Captured Radicle node id for {node}")
            generated.append((node, service))
            continue

        if service == "git-annex":
            if args.dry_run:
                print(f"Would derive git-annex endpoint for {node} -> {source_ledger_for_service(service)}")
            else:
                payload = derive_git_annex_payload(inventory, node)
                update_identity_source_file(args.flake, service, node, generated_identity_record(service, node, payload))
                print(f"Derived git-annex endpoint for {node}")
            generated.append((node, service))
            continue

        unsupported.append((node, service))

    if unsupported:
        print("\nStill manual:")
        for node, service in unsupported:
            print(f"  - {node}/{service} -> {source_ledger_for_service(service)}")

    if generated and not args.dry_run and args.publish:
        generated_nodes = sorted({node for node, _service in generated})
        generated_services = sorted({service for _node, service in generated}, key=service_sort_key)
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
        cmd_identity_publish(publish_args)

    if unsupported:
        return 1
    return 0


def public_from_inventory_data(inventory: dict, node: str, service: str) -> dict:
    identity_record = ((((inventory.get("identities") or {}).get("services") or {}).get(service) or {}).get(node))
    if identity_record:
        public = public_from_identity_record(identity_record)
        if public:
            return public
    if service == "yggdrasil":
        ygg_node = (((inventory.get("networks") or {}).get("privateYggdrasil") or {}).get("nodes") or {}).get(node) or {}
        public = {}
        public_key = ygg_node.get("publicKey")
        address = ygg_node.get("address")
        deploy_host = ygg_node.get("deployHost") or address
        generated_at = ygg_node.get("generatedAt") or ygg_node.get("keyGeneratedAt") or ygg_node.get("sourceTimestamp")
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
    for _path, event in registry.load_events(registry_path):
        subject = event.get("subject") or {}
        if (
            subject.get("node") == node
            and subject.get("service") == service
            and event.get("generation") == generation
            and event.get("state") == state
            and (event.get("public") or {}) == public
            and event.get("privateDelivery") == private_delivery
        ):
            return True
    return False


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
) -> Path | None:
    if (
        not allow_duplicate
        and registry_already_has_identity(registry_path, node, service, generation, state, public, private_delivery)
    ):
        print(f"Registry already has {node}/{service} generation {generation} in state {state}")
        return None
    event_id = new_event_id("identity")
    try:
        leader_public_key = leader_key_arg or leader_key(policy, leader)
    except ValueError as error:
        raise ValueError(str(error)) from error
    event = {
        "schema": "cluster.identity.event.v1",
        "eventId": event_id,
        "leader": leader,
        "leaderKey": leader_public_key,
        "leaderPolicyEpoch": int((policy.get("policy") or policy).get("leaderPolicyEpoch", 1)),
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
    attach_signature(event, signing_key, signature, policy)
    path = event_path(registry_path, event_id)
    write_json(path, event)
    failures = registry.validate_registry(registry_path, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise ValueError("registry validation failed after writing identity event")
    commit(registry_path, f"identity publish {node} {service} gen {generation}", not no_commit)
    return path


def cmd_identity_publish_public(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    public = public_from_inventory(args.flake, args.node, args.service) if args.from_inventory else {}
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
    inventory = transport.inventory(args.flake)
    nodes = sorted((((inventory.get("networks") or {}).get("privateYggdrasil") or {}).get("nodes") or {}).keys())
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
            )
        except ValueError as error:
            print(error, file=sys.stderr)
            failed += 1
            continue
        if path is not None:
            published += 1
            print(path)
    print(f"Published {published} {args.service} public identity event(s) from flake inventory")
    if failed:
        print(f"Failed to publish {failed} identity event(s)", file=sys.stderr)
        return 1
    return 0


def cmd_identity_publish(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    ensure_registry_git_repo(args.registry)
    if args.fetch:
        transport.git_fetch_all(args.registry, policy)
    inventory = transport.inventory(args.flake)
    services = normalize_filter_values(args.service)
    nodes = normalize_filter_values(args.node)
    published = 0
    unchanged = 0
    failed = 0
    for node, service, record, public, private_delivery, record_generation, record_state in flake_identity_records(inventory, services, nodes):
        generation = args.generation if args.generation is not None else record_generation
        state = args.state or record_state
        if not isinstance(generation, int):
            print(f"Skipping {node}/{service}: generation is not an integer", file=sys.stderr)
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
    if published:
        commit(args.registry, "identity publish flake ledger", not args.no_commit)
    if not args.no_reconcile:
        try:
            registry.reconcile(args.registry, args.out, policy)
        except PermissionError as error:
            print(f"Skipping local materialization: {error}", file=sys.stderr)
    pushed: list[str] = []
    if args.push:
        pushed = transport.git_push_remotes(args.registry, args.remote, policy)
    if args.notify:
        targets = resolve_hosts_arg(args.node, inventory)
        notify.notify_targets(targets, args.out, args.flake)
    print(f"Published {published} flake identity event(s); {unchanged} already current")
    if pushed:
        print(f"Pushed registry remotes: {', '.join(pushed)}")
    elif args.push:
        print("No Git remotes configured for registry push")
    if failed:
        print(f"Failed to publish {failed} identity event(s)", file=sys.stderr)
        return 1
    return 0


def find_event(registry_path: Path, node: str, service: str, generation: int) -> dict | None:
    for _path, event in registry.load_events(registry_path):
        subject = event.get("subject") or {}
        if subject.get("node") == node and subject.get("service") == service and event.get("generation") == generation:
            return event
    return None


def cmd_identity_promote(args) -> int:
    base = find_event(args.registry, args.node, args.service, args.generation)
    if not base:
        print(f"No event found for {args.node}/{args.service} generation {args.generation}", file=sys.stderr)
        return 1
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    event_id = new_event_id("identity")
    promoted = dict(base)
    try:
        promoted.update(
            {
                "eventId": event_id,
                "leader": leader,
                "leaderKey": args.leader_key or leader_key(policy, leader),
                "state": "active",
                "supersedes": [base.get("eventId")],
                "createdAt": now_utc(),
            }
        )
        attach_signature(promoted, args.signing_key, args.signature, policy)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    write_json(event_path(args.registry, event_id), promoted)
    failures = registry.validate_registry(args.registry, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    commit(args.registry, f"identity promote {args.node} {args.service} gen {args.generation}", not args.no_commit)
    print(event_path(args.registry, event_id))
    return 0


def cmd_identity_burn(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    event_id = new_event_id("burn")
    try:
        event = {
            "schema": "cluster.identity.event.v1",
            "eventId": event_id,
            "leader": leader,
            "leaderKey": args.leader_key or leader_key(policy, leader),
            "leaderPolicyEpoch": int((policy.get("policy") or policy).get("leaderPolicyEpoch", 1)),
            "subject": {
                "node": args.node,
                "service": args.service,
            },
            "generation": args.generation,
            "state": "burned",
            "burned": {
                "fingerprint": args.fingerprint,
                "reason": args.reason,
            },
            "createdAt": now_utc(),
        }
        attach_signature(event, args.signing_key, args.signature, policy)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    write_json(event_path(args.registry, event_id), event)
    failures = registry.validate_registry(args.registry, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    commit(args.registry, f"identity burn {args.node} {args.service} gen {args.generation}", not args.no_commit)
    print(event_path(args.registry, event_id))
    return 0


def cmd_identity_status(args) -> int:
    state = read_json(args.out / "active.json", {}) or {}
    node_state = (state.get("nodes") or {}).get(args.node) if args.node else state.get("nodes", {})
    print(json.dumps(node_state or {}, indent=2, sort_keys=True))
    return 0


def cmd_identity_apply(args) -> int:
    from .apply import apply_materialized

    apply_materialized(args.registry, args.out, load_policy(args.policy))
    print(f"Applied materialized identity state from {args.out}")
    return 0


def resolve_target(host: str, flake: str) -> tuple[str, str]:
    bootstrap = transport.host_bootstrap(flake).get(host, {})
    return bootstrap.get("targetHost") or host, bootstrap.get("sshUser") or "root"


def resolve_bootstrap_target(host: str, flake: str) -> tuple[str, str, str | None]:
    bootstrap = transport.host_bootstrap(flake).get(host, {})
    return (
        bootstrap.get("targetHost") or host,
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
        "smokeToken": hashlib.sha256(f"{run_id}:{phase}:{sequence}:{node}".encode("utf-8")).hexdigest()[:24],
    }


def smoke_fingerprint(run_id: str, service: str, node: str, generation: int) -> str:
    payload = f"{run_id}:{service}:{node}:{generation}"
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ssh_run(host: str, flake: str, remote_command: str, *, capture_output: bool = False) -> subprocess.CompletedProcess:
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
        completed = ssh_run(host, flake, "systemctl start cluster-identity-fetch-now.service")
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
        f"&& grep -q '\"state\": \"{expected_state}\"' {shlex.quote(remote_file)}"
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
        raise RuntimeError(f"timed out waiting for remote event {relative_event_path} on: {waiting}")


def ensure_remote_registry_clean(hosts: list[str], flake: str, remote_registry_path: str) -> None:
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
            raise RuntimeError(f"remote registry worktree is dirty on {host}: {completed.stdout.strip()}")


def prepare_remote_smoke_hosts(hosts: list[str], flake: str, remote_registry_path: str) -> None:
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


def remote_state_entry(host: str, flake: str, out: Path, state_file: str, node: str, service: str) -> dict | None:
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
        "leaderKey": leader_key_arg or leader_key(policy, leader),
        "leaderPolicyEpoch": int((policy.get("policy") or policy).get("leaderPolicyEpoch", 1)),
        "subject": {
            "node": node,
            "service": service,
        },
        "generation": generation,
        "state": "burned",
        "burned": {
            "fingerprint": fingerprint,
            "reason": reason,
        },
        "createdAt": now_utc(),
    }
    attach_signature(event, signing_key, None, policy)
    path = event_path(registry_path, event_id)
    write_json(path, event)
    failures = registry.validate_registry(registry_path, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise RuntimeError("registry validation failed after burning smoke identity")
    commit(registry_path, f"identity burn {node} {service} gen {generation}", not no_commit)
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
        raise RuntimeError(f"no staged smoke event found for {node}/{service} generation {generation}")
    promoted = dict(base)
    promoted.update(
        {
            "eventId": new_event_id("identity"),
            "leader": leader,
            "leaderKey": leader_key_arg or leader_key(policy, leader),
            "state": "active",
            "supersedes": [base.get("eventId")],
            "createdAt": now_utc(),
        }
    )
    attach_signature(promoted, signing_key, None, policy)
    path = event_path(registry_path, promoted["eventId"])
    write_json(path, promoted)
    failures = registry.validate_registry(registry_path, policy)
    if failures:
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        raise RuntimeError("registry validation failed after promoting smoke identity")
    commit(registry_path, f"identity promote {node} {service} gen {generation}", not no_commit)
    return path


def smoke_push_and_fetch(registry_path: Path, policy: dict, verify_hosts: list[str], flake: str) -> None:
    pushed = smoke_push_remotes(registry_path, policy)
    if not pushed:
        raise RuntimeError("no Git remotes configured for smoke-test push")
    ensure_remote_registry_clean(
        verify_hosts,
        flake,
        policy.get("registryPath") or str(DEFAULT_REGISTRY),
    )


def smoke_remote_names(policy: dict) -> list[str]:
    fallback = [name for name in transport.policy_remotes(policy, "push") if "fallback" in name]
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
    transport_policy = ((policy.get("registry") or {}).get("transport") or {})
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


def cmd_identity_smoke_test(args) -> int:
    policy = load_policy(args.policy)
    leader = args.leader or socket.gethostname()
    inventory = transport.inventory(args.flake)
    selected_nodes = resolve_hosts_arg(args.node or operator_hosts(inventory), inventory)
    verify_hosts = resolve_hosts_arg(args.verify_node or operator_hosts(inventory), inventory)
    signing_key = args.signing_key
    run_id = now_utc().replace(":", "").replace("-", "")
    remote_registry_path = policy.get("registryPath") or str(DEFAULT_REGISTRY)
    services = {
        "one": "smoke-identity-one",
        "bulk": "smoke-identity-bulk",
        "stress": "smoke-identity-stress",
    }

    ensure_registry_git_repo(args.registry)
    transport.sync_git_remotes(args.registry, ((policy.get("registry") or {}).get("remotes") or {}), False)
    smoke_fetch_remotes(args.registry, policy)

    print(f"Smoke test run: {run_id}")
    print(f"Rollout nodes: {', '.join(selected_nodes)}")
    print(f"Verification hosts: {', '.join(verify_hosts)}")

    try:
        prepare_remote_smoke_hosts(verify_hosts, args.flake, remote_registry_path)
        ensure_remote_registry_clean(verify_hosts, args.flake, remote_registry_path)

        print("\n[1/3] One-at-a-time rollout")
        for index, node in enumerate(selected_nodes, 1):
            service = services["one"]
            generation = next_generation(args.registry, node, service)
            public = smoke_public_payload(run_id, "one-at-a-time", index, node)
            staged_path = write_smoke_event(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                signing_key=signing_key,
                node=node,
                service=service,
                generation=generation,
                state="staged",
                public=public,
            )
            smoke_push_and_fetch(args.registry, policy, verify_hosts, args.flake)
            wait_for_remote_event(
                verify_hosts,
                args.flake,
                remote_registry_path,
                str(staged_path.relative_to(args.registry)),
                "staged",
                generation,
                timeout_seconds=args.poll_seconds,
                interval_seconds=args.poll_interval,
            )
            active_path = smoke_promote(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                signing_key=signing_key,
                node=node,
                service=service,
                generation=generation,
            )
            smoke_push_and_fetch(args.registry, policy, verify_hosts, args.flake)
            wait_for_remote_event(
                verify_hosts,
                args.flake,
                remote_registry_path,
                str(active_path.relative_to(args.registry)),
                "active",
                generation,
                timeout_seconds=args.poll_seconds,
                interval_seconds=args.poll_interval,
            )
            fingerprint = smoke_fingerprint(run_id, service, node, generation)
            burn_path = burn_smoke_event(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                signing_key=signing_key,
                node=node,
                service=service,
                generation=generation,
                fingerprint=fingerprint,
                reason="smoke test cleanup",
            )
            smoke_push_and_fetch(args.registry, policy, verify_hosts, args.flake)
            wait_for_remote_event(
                verify_hosts,
                args.flake,
                remote_registry_path,
                str(burn_path.relative_to(args.registry)),
                "burned",
                generation,
                timeout_seconds=args.poll_seconds,
                interval_seconds=args.poll_interval,
            )
            print(f"  {node}: staged -> active -> burned generation {generation}")

        print("\n[2/3] Bulk rollout")
        bulk_service = services["bulk"]
        bulk_generations: dict[str, tuple[int, str]] = {}
        for index, node in enumerate(selected_nodes, 1):
            generation = next_generation(args.registry, node, bulk_service)
            bulk_path = write_smoke_event(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                signing_key=signing_key,
                node=node,
                service=bulk_service,
                generation=generation,
                state="staged",
                public=smoke_public_payload(run_id, "bulk", index, node),
            )
            bulk_generations[node] = (generation, str(bulk_path.relative_to(args.registry)))
        smoke_push_and_fetch(args.registry, policy, verify_hosts, args.flake)
        for node, (generation, staged_relpath) in bulk_generations.items():
            wait_for_remote_event(
                verify_hosts,
                args.flake,
                remote_registry_path,
                staged_relpath,
                "staged",
                generation,
                timeout_seconds=args.poll_seconds,
                interval_seconds=args.poll_interval,
            )
        bulk_active_paths: dict[str, tuple[int, str]] = {}
        for node, (generation, _staged_relpath) in bulk_generations.items():
            active_path = smoke_promote(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                signing_key=signing_key,
                node=node,
                service=bulk_service,
                generation=generation,
            )
            bulk_active_paths[node] = (generation, str(active_path.relative_to(args.registry)))
        smoke_push_and_fetch(args.registry, policy, verify_hosts, args.flake)
        for node, (generation, active_relpath) in bulk_active_paths.items():
            wait_for_remote_event(
                verify_hosts,
                args.flake,
                remote_registry_path,
                active_relpath,
                "active",
                generation,
                timeout_seconds=args.poll_seconds,
                interval_seconds=args.poll_interval,
            )
        bulk_burn_paths: dict[str, tuple[int, str]] = {}
        for node, (generation, _active_relpath) in bulk_active_paths.items():
            fingerprint = smoke_fingerprint(run_id, bulk_service, node, generation)
            burn_path = burn_smoke_event(
                registry_path=args.registry,
                policy=policy,
                leader=leader,
                leader_key_arg=args.leader_key,
                signing_key=signing_key,
                node=node,
                service=bulk_service,
                generation=generation,
                fingerprint=fingerprint,
                reason="smoke test cleanup",
            )
            bulk_burn_paths[node] = (generation, str(burn_path.relative_to(args.registry)))
        smoke_push_and_fetch(args.registry, policy, verify_hosts, args.flake)
        for node, (generation, burn_relpath) in bulk_burn_paths.items():
            wait_for_remote_event(
                verify_hosts,
                args.flake,
                remote_registry_path,
                burn_relpath,
                "burned",
                generation,
                timeout_seconds=args.poll_seconds,
                interval_seconds=args.poll_interval,
            )
        print(f"  bulk verified for: {', '.join(selected_nodes)}")

        print("\n[3/3] Stress rounds")
        stress_service = services["stress"]
        for round_number in range(1, args.stress_rounds + 1):
            round_generations: dict[str, tuple[int, str]] = {}
            for node in selected_nodes:
                generation = next_generation(args.registry, node, stress_service)
                active_path = write_smoke_event(
                    registry_path=args.registry,
                    policy=policy,
                    leader=leader,
                    leader_key_arg=args.leader_key,
                    signing_key=signing_key,
                    node=node,
                    service=stress_service,
                    generation=generation,
                    state="active",
                    public=smoke_public_payload(run_id, f"stress-round-{round_number}", generation, node),
                )
                round_generations[node] = (generation, str(active_path.relative_to(args.registry)))
            smoke_push_and_fetch(args.registry, policy, verify_hosts, args.flake)
            for node, (generation, active_relpath) in round_generations.items():
                wait_for_remote_event(
                    verify_hosts,
                    args.flake,
                    remote_registry_path,
                    active_relpath,
                    "active",
                    generation,
                    timeout_seconds=args.poll_seconds,
                    interval_seconds=args.poll_interval,
                )
            round_burn_paths: dict[str, tuple[int, str]] = {}
            for node, (generation, _active_relpath) in round_generations.items():
                fingerprint = smoke_fingerprint(run_id, stress_service, node, generation)
                burn_path = burn_smoke_event(
                    registry_path=args.registry,
                    policy=policy,
                    leader=leader,
                    leader_key_arg=args.leader_key,
                    signing_key=signing_key,
                    node=node,
                    service=stress_service,
                    generation=generation,
                    fingerprint=fingerprint,
                    reason=f"smoke stress cleanup round {round_number}",
                )
                round_burn_paths[node] = (generation, str(burn_path.relative_to(args.registry)))
            smoke_push_and_fetch(args.registry, policy, verify_hosts, args.flake)
            for node, (generation, burn_relpath) in round_burn_paths.items():
                wait_for_remote_event(
                    verify_hosts,
                    args.flake,
                    remote_registry_path,
                    burn_relpath,
                    "burned",
                    generation,
                    timeout_seconds=args.poll_seconds,
                    interval_seconds=args.poll_interval,
                )
            print(f"  round {round_number}: verified on {', '.join(verify_hosts)}")
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        restore_remote_smoke_hosts(verify_hosts, args.flake)

    print("\nSmoke test completed successfully")
    return 0


def cmd_bundle_publish(args) -> int:
    target_host, ssh_user = resolve_target(args.node, args.flake)
    bundles.publish_bundle(args.node, args.service, args.generation, args.source, args.target_path, target_host, ssh_user)
    print(f"Published {args.service} generation {args.generation} private material to {args.node} via {target_host}")
    return 0


def cmd_bundle_seal(args) -> int:
    policy = load_policy(args.policy)
    inventory = transport.inventory(args.flake)
    host_age = ((((inventory.get("identities") or {}).get("services") or {}).get("host-age") or {}).get(args.node) or {})
    recipient = args.recipient or (((host_age.get("public") or {}).get("ageRecipient")))
    if not recipient:
        print(f"No host-age recipient found for {args.node}", file=sys.stderr)
        return 1
    expected_public = public_from_inventory_data(inventory, args.node, args.service) if args.from_inventory else {}
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
        )
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    commit(args.registry, f"bundle seal {args.node} {args.service} gen {args.generation}", not args.no_commit)
    print(manifest)
    return 0


def cmd_receipt_write(args) -> int:
    policy = load_policy(args.policy)
    target = args.path or Path(f"/var/lib/cluster-identity/receipts/{args.node}-{args.service}-gen-{args.generation}.json")
    try:
        bundles.write_receipt(
            target,
            args.node,
            args.service,
            args.generation,
            args.status,
            args.activated,
            args.signed_by_node,
            args.signing_key or signing_key_path(policy, None),
            args.signature,
        )
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    print(target)
    return 0


def cmd_receipt_collect(args) -> int:
    target_host, ssh_user = resolve_target(args.node, args.flake)
    destination = args.registry / "receipts" / f"{args.node}-{args.service}-gen-{args.generation}.json"
    bundles.collect_receipt(args.node, args.service, args.generation, target_host, ssh_user, destination)
    commit(args.registry, f"receipt collect {args.node} {args.service} gen {args.generation}", not args.no_commit)
    print(destination)
    return 0


def cmd_deploy(args) -> int:
    inventory = transport.inventory(args.flake)
    hosts = resolve_hosts_arg(args.hosts, inventory)
    last_code = 0
    for host in hosts:
        candidates = deploy.candidates(host, args.out, args.flake)
        print(f"Resolved deploy candidates for {host}:")
        for index, (label, target) in enumerate(candidates, 1):
            print(f"  {index}. {label}: {target}")
        selected = candidates[0] if candidates else ("plain host name", host)
        print("\nSelected:")
        print(f"  {selected[0]} {selected[1]}")
        command = ["nix", "run", f"{args.flake}#deploy-rs", "--", f".#{host}"]
        print("\nRunning:")
        print("  " + " ".join(command))
        if not args.dry_run:
            code = subprocess.run(command, check=False).returncode
            last_code = code
            if code != 0:
                return code
        if host != hosts[-1]:
            print("")
    return 0


def cmd_host_age_bootstrap(args) -> int:
    target_host, ssh_user = resolve_target(args.host, args.flake)
    private_key_path = args.target_path
    generate = (
        f"(command -v age-keygen >/dev/null 2>&1 && age-keygen -o {private_key_path} "
        f"|| nix shell nixpkgs#age -c age-keygen -o {private_key_path})"
    )
    if args.source:
        remote_tmp = f"/tmp/cluster-identity-host-age-{args.host}.agekey"
        subprocess.run(["scp", str(args.source), f"{ssh_user}@{target_host}:{remote_tmp}"], check=True)
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
        ["ssh", f"{ssh_user}@{target_host}", f"sed -n 's/^# public key: //p' {private_key_path}"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    print(f"{args.host} {public}")
    return 0


def cmd_host_age_public(args) -> int:
    target_host, ssh_user = resolve_target(args.host, args.flake)
    completed = subprocess.run(
        ["ssh", f"{ssh_user}@{target_host}", f"sed -n 's/^# public key: //p' {args.target_path}"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    print(completed.stdout.strip())
    return 0


def cmd_host_age_rotate(args) -> int:
    target_host, ssh_user = resolve_target(args.host, args.flake)
    backup = f"{args.target_path}.old-{now_utc().replace(':', '').replace('-', '')}"
    generate = (
        f"(command -v age-keygen >/dev/null 2>&1 && age-keygen -o {args.target_path} "
        f"|| nix shell nixpkgs#age -c age-keygen -o {args.target_path})"
    )
    command = (
        "install -d -m 0700 /var/lib/cluster-identity/age "
        f"&& if [ -s {args.target_path} ]; then mv {args.target_path} {backup}; fi "
        f"&& {generate} "
        f"&& chmod 0400 {args.target_path}"
    )
    subprocess.run(["ssh", f"{ssh_user}@{target_host}", command], check=True)
    public = subprocess.run(
        ["ssh", f"{ssh_user}@{target_host}", f"sed -n 's/^# public key: //p' {args.target_path}"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clusterctl")
    parser.add_argument("--flake", default=os.environ.get("CLUSTERCTL_FLAKE", "."))
    sub = parser.add_subparsers(dest="command", required=True)

    reg = sub.add_parser("registry")
    reg_sub = reg.add_subparsers(dest="registry_command", required=True)
    for name, func in [
        ("init", cmd_registry_init),
        ("validate", cmd_registry_validate),
        ("reconcile", cmd_registry_reconcile),
        ("materialize", cmd_registry_materialize),
        ("sync", cmd_registry_sync),
        ("push", cmd_registry_push),
        ("notify", cmd_registry_notify),
        ("status", cmd_registry_status),
    ]:
        p = reg_sub.add_parser(name)
        add_registry_common(p)
        p.set_defaults(func=func)
    reg_sub.choices["init"].add_argument("--no-commit", action="store_true")
    reg_sub.choices["push"].add_argument("--remote", action="append")
    reg_sub.choices["push"].add_argument("--sync-remotes", action=argparse.BooleanOptionalAction, default=True)
    reg_sub.choices["push"].add_argument("--prune-remotes", action="store_true")
    reg_sub.choices["sync"].add_argument("--sync-remotes", action=argparse.BooleanOptionalAction, default=True)
    reg_sub.choices["sync"].add_argument("--prune-remotes", action="store_true")
    reg_sub.choices["notify"].add_argument("--target", action="append", default=[])
    remotes = reg_sub.add_parser("remotes")
    remotes_sub = remotes.add_subparsers(dest="remotes_command", required=True)
    remotes_sync = remotes_sub.add_parser("sync")
    add_registry_common(remotes_sync)
    remotes_sync.add_argument("--prune", action="store_true")
    remotes_sync.set_defaults(func=cmd_registry_remotes_sync)
    resign = reg_sub.add_parser("resign-placeholders")
    add_registry_common(resign)
    add_signing_common(resign)
    resign.add_argument("--no-commit", action="store_true")
    resign.set_defaults(func=cmd_registry_resign_placeholders)

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
    publish_all.add_argument("--no-commit", action="store_true")
    publish_all.add_argument("--no-reconcile", action="store_true")
    publish_all.add_argument("--fetch", action=argparse.BooleanOptionalAction, default=True)
    publish_all.add_argument("--push", action=argparse.BooleanOptionalAction, default=True)
    publish_all.add_argument("--remote", action="append")
    publish_all.add_argument("--notify", action="store_true")
    publish_all.set_defaults(func=cmd_identity_publish)

    publish = ident_sub.add_parser("publish-public")
    add_registry_common(publish)
    publish.add_argument("node")
    publish.add_argument("service")
    publish.add_argument("--generation", type=int, required=True)
    publish.add_argument("--state", choices=sorted(VALID_STATES), default="staged")
    publish.add_argument("--from-inventory", action="store_true")
    publish.add_argument("--allow-duplicate", action="store_true")
    publish.add_argument("--ssh-host-key")
    publish.add_argument("--yggdrasil-public-key")
    publish.add_argument("--yggdrasil-address")
    publish.add_argument("--deploy-host")
    publish.add_argument("--radicle-node-id")
    publish.add_argument("--git-annex-endpoint")
    publish.add_argument("--supersedes", action="append", default=[])
    publish.add_argument("--leader")
    publish.add_argument("--leader-key")
    add_signing_common(publish)
    publish.add_argument("--no-commit", action="store_true")
    publish.set_defaults(func=cmd_identity_publish_public)

    publish_inventory = ident_sub.add_parser("publish-inventory")
    add_registry_common(publish_inventory)
    publish_inventory.add_argument("--service", choices=["yggdrasil"], default="yggdrasil")
    publish_inventory.add_argument("--generation", type=int, required=True)
    publish_inventory.add_argument("--state", choices=sorted(VALID_STATES), default="staged")
    publish_inventory.add_argument("--leader")
    publish_inventory.add_argument("--leader-key")
    add_signing_common(publish_inventory)
    publish_inventory.add_argument("--allow-duplicate", action="store_true")
    publish_inventory.add_argument("--no-commit", action="store_true")
    publish_inventory.set_defaults(func=cmd_identity_publish_inventory)

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

    status = ident_sub.add_parser("status")
    add_registry_common(status)
    status.add_argument("node", nargs="?")
    status.set_defaults(func=cmd_identity_status)

    matrix = ident_sub.add_parser("matrix")
    matrix.add_argument("--node", action="append", default=[])
    matrix.add_argument("--service", action="append", default=[])
    matrix.add_argument("--only-missing", action="store_true")
    matrix.add_argument("--json", action="store_true")
    matrix.set_defaults(func=cmd_identity_matrix)

    generate_missing = ident_sub.add_parser("generate-missing")
    add_registry_common(generate_missing)
    generate_missing.add_argument("--node", action="append", default=[])
    generate_missing.add_argument("--service", action="append", default=[])
    generate_missing.add_argument("--dry-run", action="store_true")
    generate_missing.add_argument("--publish", action=argparse.BooleanOptionalAction, default=True)
    generate_missing.add_argument("--publish-push", action=argparse.BooleanOptionalAction, default=True)
    generate_missing.add_argument("--notify", action="store_true")
    generate_missing.add_argument("--no-reconcile", action="store_true")
    generate_missing.add_argument("--leader")
    generate_missing.add_argument("--leader-key")
    add_signing_common(generate_missing)
    generate_missing.add_argument("--no-commit", action="store_true")
    generate_missing.set_defaults(func=cmd_identity_generate_missing)

    smoke = ident_sub.add_parser("smoke-test")
    add_registry_common(smoke)
    smoke.add_argument("--node", action="append", default=[])
    smoke.add_argument("--verify-node", action="append", default=[])
    smoke.add_argument("--stress-rounds", type=int, default=3)
    smoke.add_argument("--poll-seconds", type=int, default=90)
    smoke.add_argument("--poll-interval", type=float, default=2.0)
    smoke.add_argument("--leader")
    smoke.add_argument("--leader-key")
    add_signing_common(smoke)
    smoke.set_defaults(func=cmd_identity_smoke_test)

    apply_p = ident_sub.add_parser("apply")
    add_registry_common(apply_p)
    apply_p.set_defaults(func=cmd_identity_apply)

    bundle = sub.add_parser("bundle")
    bundle_sub = bundle.add_subparsers(dest="bundle_command", required=True)
    publish_bundle = bundle_sub.add_parser("publish")
    publish_bundle.add_argument("node")
    publish_bundle.add_argument("service")
    publish_bundle.add_argument("--generation", type=int, required=True)
    publish_bundle.add_argument("--source", type=Path, required=True)
    publish_bundle.add_argument("--target-path", required=True)
    publish_bundle.set_defaults(func=cmd_bundle_publish)
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
    deploy_p.add_argument("hosts", nargs="+")
    deploy_p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    deploy_p.add_argument("--dry-run", action="store_true")
    deploy_p.set_defaults(func=cmd_deploy)

    host_age = sub.add_parser("host-age")
    host_age_sub = host_age.add_subparsers(dest="host_age_command", required=True)
    bootstrap = host_age_sub.add_parser("bootstrap")
    bootstrap.add_argument("host")
    bootstrap.add_argument("--source", type=Path)
    bootstrap.add_argument("--target-path", default="/var/lib/cluster-identity/age/host.agekey")
    bootstrap.set_defaults(func=cmd_host_age_bootstrap)
    public = host_age_sub.add_parser("public")
    public.add_argument("host")
    public.add_argument("--target-path", default="/var/lib/cluster-identity/age/host.agekey")
    public.set_defaults(func=cmd_host_age_public)
    rotate = host_age_sub.add_parser("rotate")
    rotate.add_argument("host")
    rotate.add_argument("--target-path", default="/var/lib/cluster-identity/age/host.agekey")
    rotate.set_defaults(func=cmd_host_age_rotate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
