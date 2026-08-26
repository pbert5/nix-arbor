"""Small, deterministic local control surface for an Arbor Registry runtime."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from nacl.signing import SigningKey

from .runtime import (
    OrbitDBProvider,
    Runtime,
    RuntimeKey,
    canonical_json,
    make_public_record,
    make_identity_generation,
    generate_keypair,
    make_recovery_approval,
    make_recovery_authorization,
)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _write_json_atomic(path: Path, value: Any, *, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _private_key(path: Path, issuer: str, generation: int | None = None) -> RuntimeKey:
    suffix = f".g{generation}" if generation is not None else ""
    private = path / f"{issuer}{suffix}.private"
    # Bootstrap authorities and legacy generation-one identities may retain
    # their unsuffixed key.  Never use it for a requested later generation:
    # that would produce a record claiming a generation the key cannot sign.
    if generation == 1 and not private.exists():
        private = path / f"{issuer}.private"
    if not private.exists():
        raise ValueError(f"private key for issuer {issuer!r}, generation {generation or 'legacy'} is missing")
    encoded = private.read_text(encoding="ascii").strip()
    signing = SigningKey(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    return RuntimeKey(issuer, signing)


def _config(path: Path) -> dict[str, Any]:
    value = _read_json(path, {})
    if not isinstance(value, dict):
        raise ValueError("runtime config must be a JSON object")
    required = ("stateDir", "transportSocket", "transportTokenFile", "bootstrapAuthoritiesFile", "identityDir")
    if any(not isinstance(value.get(key), str) or not value[key] for key in required):
        raise ValueError("runtime config is missing a required path")
    return value


def _runtime(config: dict[str, Any]) -> tuple[Runtime, OrbitDBProvider]:
    state = Path(config["stateDir"])
    authorities = _read_json(Path(config["bootstrapAuthoritiesFile"]), {})
    if isinstance(authorities, dict) and isinstance(authorities.get("keys"), dict):
        authorities = authorities["keys"]
    if not isinstance(authorities, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in authorities.items()):
        raise ValueError("bootstrap authorities must be a mapping of issuer to public key")
    identities = Path(config["identityDir"])
    keys = dict(authorities)
    for public in identities.glob("*.public"):
        keys[public.name.removesuffix(".public")] = public.read_text(encoding="ascii").strip()
    token = Path(config["transportTokenFile"]).read_text(encoding="utf-8").strip()
    provider = OrbitDBProvider(
        Path(config["transportSocket"]), config.get("stream", "registry"), token=token,
        timeout=float(config.get("transportTimeout", 30)),
    )
    runtime = Runtime(
        state, provider, keys,
        authority_issuers=set(config.get("authorityIssuers", authorities.keys())),
    )
    return runtime, provider


def _format(value: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    elif isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
    else:
        print(value)


def _sync(config: dict[str, Any], runtime: Runtime, provider: OrbitDBProvider, limit: int, pages: int) -> dict[str, Any]:
    cursor_path = Path(config.get("providerCursorFile", Path(config["stateDir"]) / "provider-cursor.json"))
    saved = _read_json(cursor_path, {})
    cursor = saved.get("cursor", "v2:begin") if isinstance(saved, dict) else "v2:begin"
    fetched = accepted = quarantined = 0
    for _ in range(pages):
        records = provider.fetch(cursor, limit)
        next_cursor = provider.next_cursor
        if not records:
            break
        outcomes = runtime.ingest(record for _, record in records)
        fetched += len(records)
        accepted += sum(item.get("status") == "accepted" for item in outcomes)
        quarantined += sum(item.get("status") == "quarantined" for item in outcomes)
        if not isinstance(next_cursor, str) or next_cursor == cursor:
            break
        cursor = next_cursor
        # Persist only after the entire page has been ingested and reconciled.
        _write_json_atomic(cursor_path, {"cursor": cursor})
        if len(records) < limit:
            break
    return {"fetched": fetched, "accepted": accepted, "quarantined": quarantined, "cursor": cursor}


def _record(
    key: RuntimeKey,
    schema: str,
    record_id: str,
    payload: dict[str, Any],
    generation: int = 1,
    issuer_generation: int | None = None,
) -> dict[str, Any]:
    if not schema or not record_id or not isinstance(payload, dict):
        raise ValueError("schema, record id, and object payload are required")
    return make_public_record(
        key, schema, record_id, payload, generation=generation, issuer_generation=issuer_generation,
    )


def _authority_issuers(config: dict[str, Any]) -> set[str]:
    authorities = _read_json(Path(config["bootstrapAuthoritiesFile"]), {})
    if isinstance(authorities, dict) and isinstance(authorities.get("keys"), dict):
        authorities = authorities["keys"]
    configured = config.get("authorityIssuers")
    if configured is not None:
        if not isinstance(configured, list) or any(not isinstance(item, str) for item in configured):
            raise ValueError("authorityIssuers must be a list of issuer names")
        return set(configured)
    return set(authorities) if isinstance(authorities, dict) else set()


def _public_generations(args: argparse.Namespace, config: dict[str, Any]) -> tuple[int, int | None]:
    legacy = getattr(args, "generation", None)
    record_generation = getattr(args, "record_generation", None)
    issuer_generation = getattr(args, "issuer_generation", None)
    if legacy is not None and (record_generation is not None or issuer_generation is not None):
        raise ValueError("--generation cannot be combined with --record-generation or --issuer-generation")
    if legacy is not None:
        record_generation = issuer_generation = legacy
    elif record_generation is None and issuer_generation is None:
        # The historical default emitted generation one in both fields.
        record_generation, issuer_generation = 1, 1
    elif record_generation is None:
        record_generation = 1
    if isinstance(record_generation, bool) or not isinstance(record_generation, int) or record_generation < 1:
        raise ValueError("record generation must be a positive integer")
    if issuer_generation is not None and (
        isinstance(issuer_generation, bool) or not isinstance(issuer_generation, int) or issuer_generation < 1
    ):
        raise ValueError("issuer generation must be a positive integer")
    if issuer_generation is None and args.issuer not in _authority_issuers(config):
        raise ValueError("--issuer-generation is required for a non-authority issuer")
    return record_generation, issuer_generation


def _public_command(args: argparse.Namespace, config: dict[str, Any], schema: str, required: tuple[str, ...]) -> dict[str, Any]:
    record_generation, issuer_generation = _public_generations(args, config)
    payload = {field: getattr(args, field) for field in required}
    key = _private_key(Path(config["identityDir"]), args.issuer, issuer_generation)
    runtime, _ = _runtime(config)
    try:
        result = runtime.ingest([_record(key, schema, args.record_id, payload, record_generation, issuer_generation)])
        return result[0]
    finally:
        runtime.close()


def _data_only(value: Any) -> Any:
    blocked = {"secret", "password", "token", "credential", "private", "privatekey", "signingkey",
               "code", "script", "command", "executable"}
    if isinstance(value, dict):
        return {key: _data_only(item) for key, item in sorted(value.items())
                if key.replace("-", "").replace("_", "").lower() not in blocked}
    if isinstance(value, list):
        return [_data_only(item) for item in value]
    return value


def manager_snapshot(value: dict[str, Any]) -> dict[str, Any]:
    """Export Manager's public node-data contract with a stable digest."""
    source = value.get("nodes", value.get("snapshot", {}).get("nodes", value))
    if not isinstance(source, dict):
        raise ValueError("manager snapshot must contain a nodes object")
    snapshot = {"nodes": {name: _data_only(source[name]) for name in sorted(source)}}
    digest = hashlib.sha256(canonical_json(snapshot)).hexdigest()
    return {"format": "arbor-manager/registry-snapshot", "version": 1,
            "snapshot": snapshot, "snapshotDigest": digest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arbor-registryctl")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--format", choices=("human", "json"), default="human")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync").add_argument("--limit", type=int, default=100)
    sub.choices["sync"].add_argument("--pages", type=int, default=100)
    for name in ("status", "accepted", "projection", "quarantine"):
        sub.add_parser(name)
    record = sub.add_parser("submit")
    record.add_argument("schema")
    record.add_argument("record_id")
    record.add_argument("payload", type=Path)
    record.add_argument("--issuer", required=True)
    record.add_argument("--record-generation", type=int)
    record.add_argument("--issuer-generation", type=int)
    record.add_argument("--generation", type=int, help=argparse.SUPPRESS)
    keygen = sub.add_parser("keygen")
    keygen.add_argument("issuer")
    keygen.add_argument("--generation", type=int)
    keygen.add_argument("--rotation", action="store_true")
    for name, schema in (("configuration-intent-publish", "configuration-intent"),
                         ("compatibility-publish", "compatibility")):
        command = sub.add_parser(name)
        command.set_defaults(schema=schema)
        command.add_argument("record_id")
        command.add_argument("payload", type=Path)
        command.add_argument("--issuer", required=True)
        command.add_argument("--record-generation", type=int, default=1)
        command.add_argument("--issuer-generation", type=int)
    approve = sub.add_parser("recovery-approve")
    approve.add_argument("identity")
    approve.add_argument("lost_generation", type=int)
    approve.add_argument("--role", required=True)
    approve.add_argument("--approver", required=True)
    approve.add_argument("--approver-generation", type=int, required=True)
    authorize = sub.add_parser("recovery-authorize")
    authorize.add_argument("identity")
    authorize.add_argument("lost_generation", type=int)
    authorize.add_argument("new_public_key")
    authorize.add_argument("approvals", type=Path)
    authorize.add_argument("--issuer", required=True)
    recover = sub.add_parser("identity-recover")
    recover.add_argument("identity")
    recover.add_argument("lost_generation", type=int)
    recover.add_argument("new_public_key")
    recover.add_argument("approvals", type=Path)
    recover.add_argument("--issuer", required=True)
    snapshot = sub.add_parser("manager-snapshot-export")
    snapshot.add_argument("input", type=Path)
    snapshot.add_argument("--output", type=Path)
    identity = sub.add_parser("identity-generation")
    identity.add_argument("identity")
    identity.add_argument("public_key")
    identity.add_argument("--issuer", required=True)
    identity.add_argument("--generation", type=int, default=1)
    relationship = sub.add_parser("relationship-add")
    relationship.add_argument("record_id")
    relationship.add_argument("--from", dest="from_node", required=True)
    relationship.add_argument("--to", dest="to_node", required=True)
    relationship.add_argument("--kind", choices=("parent", "peer"), required=True)
    relationship.add_argument("--state", choices=("active", "standby", "suspended", "severed"), default="active")
    relationship.add_argument("--authority-root", required=True)
    relationship.add_argument("--issuer", required=True)
    relationship.add_argument("--record-generation", type=int)
    relationship.add_argument("--issuer-generation", type=int)
    relationship.add_argument("--generation", type=int, help=argparse.SUPPRESS)
    for name, schema, fields in (
        ("endpoint-publish", "endpoint", ("node", "network", "address", "port", "purpose")),
        ("service-publish", "service", ("name", "node", "protocol", "endpoint")),
        ("machine-publish", "machine-facts", ("node", "system", "hostname")),
    ):
        command = sub.add_parser(name)
        command.add_argument("record_id")
        command.add_argument("--issuer", required=True)
        command.add_argument("--record-generation", type=int)
        command.add_argument("--issuer-generation", type=int)
        command.add_argument("--generation", type=int, help=argparse.SUPPRESS)
        for field in fields:
            command.add_argument(f"--{field}", required=True, type=int if field == "port" else str)
    args = parser.parse_args(argv)
    as_json = args.format == "json"
    if args.command == "manager-snapshot-export":
        result = manager_snapshot(_read_json(args.input))
        if args.output:
            _write_json_atomic(args.output, result)
        _format(result, as_json)
        return 0
    if args.config is None:
        parser.error("--config is required for this command")
    config = _config(args.config)
    if args.command == "keygen":
        key = generate_keypair(Path(config["identityDir"]), args.issuer, generation=args.generation, rotation=args.rotation)
        result = {"issuer": key.issuer, "generation": args.generation, "publicKey": key.public_key}
    elif args.command == "submit":
        payload = _read_json(args.payload, None)
        result = _public_command(argparse.Namespace(**vars(args), **payload), config, args.schema, tuple(payload))
    else:
        runtime, provider = _runtime(config)
        try:
            if args.command == "sync":
                result = _sync(config, runtime, provider, args.limit, args.pages)
            elif args.command == "status":
                result = {"runtime": runtime.status(), "transport": provider.status()}
            elif args.command == "accepted":
                result = runtime.accepted()
            elif args.command == "projection":
                result = runtime.projection()
            elif args.command == "quarantine":
                result = runtime.quarantine()
            elif args.command == "relationship-add":
                record_generation, issuer_generation = _public_generations(args, config)
                payload = {"from": args.from_node, "to": args.to_node, "kind": args.kind,
                           "status": args.state, "authorityRoot": args.authority_root}
                key = _private_key(Path(config["identityDir"]), args.issuer, issuer_generation)
                result = runtime.ingest([_record(key, "relationship", args.record_id, payload,
                                                 record_generation, issuer_generation)])[0]
            elif args.command == "identity-generation":
                key = _private_key(Path(config["identityDir"]), args.issuer)
                record = make_identity_generation(key, args.identity, args.generation, args.public_key)
                result = runtime.ingest([record])[0]
            elif args.command in {"configuration-intent-publish", "compatibility-publish"}:
                payload = _read_json(args.payload, None)
                if not isinstance(payload, dict):
                    raise ValueError("publication payload must be a JSON object")
                result = _public_command(argparse.Namespace(**vars(args), **payload), config,
                                         args.schema, tuple(payload))
            elif args.command == "recovery-approve":
                result = make_recovery_approval(
                    _private_key(Path(config["identityDir"]), args.approver),
                    args.identity, args.lost_generation, role=args.role,
                    approver_generation=args.approver_generation,
                )
            elif args.command in {"recovery-authorize", "identity-recover"}:
                authority = _private_key(Path(config["identityDir"]), args.issuer)
                approvals = _read_json(args.approvals)
                if not isinstance(approvals, list):
                    raise ValueError("approvals must be a JSON list")
                authorization = make_recovery_authorization(
                    authority, args.identity, args.lost_generation,
                    args.new_public_key, approvals,
                )
                if args.command == "identity-recover":
                    generation = make_identity_generation(
                        authority, args.identity, args.lost_generation + 1,
                        args.new_public_key,
                        predecessor=f"{args.identity}:{args.lost_generation}",
                        recovery_authorization=authorization,
                    )
                    result = runtime.ingest([authorization, generation])[1]
                else:
                    result = runtime.ingest([authorization])[0]
            else:
                schemas = {"endpoint-publish": ("endpoint", ("node", "network", "address", "port", "purpose")),
                           "service-publish": ("service", ("name", "node", "protocol", "endpoint")),
                           "machine-publish": ("machine-facts", ("node", "system", "hostname"))}
                schema, fields = schemas[args.command]
                result = _public_command(args, config, schema, fields)
        finally:
            runtime.close()
    _format(result, as_json)
    return 0
