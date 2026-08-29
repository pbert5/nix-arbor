"""Durable record ingestion; private keys and public state have separate roots."""

from __future__ import annotations

import base64
import binascii
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import fcntl
import socket
import stat
import subprocess
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, TypeAlias

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey


SCHEMAS = frozenset({
    "node-identity", "identity-generation", "relationship", "capability", "service", "endpoint",
    "enrollment", "revocation", "recovery-authorization", "receipt",
})
ProviderCursor: TypeAlias = int | str
_SECRET_NAMES = {"secret", "password", "passphrase", "token", "credential", "private", "privatekey", "signingkey", "apikey", "accesskey", "accesstoken", "seed"}
AGE_BINARY = "/run/current-system/sw/bin/age"
MAX_RECOVERY_BYTES = 16 * 1024 * 1024


def _unsafe_value(value: Any) -> bool:
    if isinstance(value, str):
        return (
            value.startswith(("/nix/store/", "/run/secrets/", "-----BEGIN"))
            or value.startswith(("AGE-SECRET-", "AGE-ENCRYPTED-"))
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://[^/?#\s]+:[^/?#\s]+@", value) is not None
            or re.match(r"^Bearer\s+\S+$", value, re.IGNORECASE) is not None
        )
    if isinstance(value, dict):
        return any(
            re.sub(r"[-_]", "", str(key)).lower() in _SECRET_NAMES or _unsafe_value(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_unsafe_value(item) for item in value)
    return False


def _secure_directory(path: Path) -> None:
    path = Path(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError(f"runtime directory is not private: {path}")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError(f"runtime directory has unexpected owner: {path}")


def _secure_file(path: Path) -> None:
    if not path.exists():
        return
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError(f"runtime file is not private: {path}")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError(f"runtime file has unexpected owner: {path}")


def canonical_json(value: Any) -> bytes:
    """The wire canonical form: UTF-8, sorted keys, no insignificant whitespace."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _without_signature(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "signature"}


def _key(record: dict[str, Any]) -> str:
    return f"{record.get('recordId')}:{record.get('recordVersion')}"


def _digest(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(record)).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class RuntimeKey:
    issuer: str
    signing_key: SigningKey

    @property
    def public_key(self) -> str:
        return _b64(bytes(self.signing_key.verify_key))

    def sign(self, unsigned: dict[str, Any]) -> str:
        return _b64(self.signing_key.sign(canonical_json(unsigned)).signature)


def make_enrollment_request(
    identity_key: RuntimeKey,
    node_id: str,
    *,
    platform: str,
    requested_parent: str | None = None,
    nonce: str | None = None,
) -> dict[str, Any]:
    """Create a self-signed enrollment request using runtime-held identity.

    The request is not authority.  It only proves possession of the proposed
    node key; an existing authority must approve it before a node-identity
    record can enter accepted state.
    """
    if not isinstance(node_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", node_id):
        raise ValueError("node_id is invalid")
    if not isinstance(platform, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", platform):
        raise ValueError("platform is invalid")
    if requested_parent is not None and not isinstance(requested_parent, str):
        raise ValueError("requested_parent is invalid")
    if nonce is None:
        nonce = _b64(os.urandom(24))
    if not isinstance(nonce, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,256}", nonce):
        raise ValueError("nonce is invalid")
    unsigned = {
        "kind": "arbor-enrollment-request",
        "version": 1,
        "nodeId": node_id,
        "generation": 1,
        "platform": platform,
        "publicKey": identity_key.public_key,
        "requestedParent": requested_parent,
        "nonce": nonce,
        "subject": identity_key.issuer,
    }
    return {**unsigned, "signature": identity_key.sign(unsigned)}


def approve_enrollment(
    request: dict[str, Any],
    authority_key: RuntimeKey,
    *,
    authority_root: str | None = None,
    relationship_scope: str = "dependent",
) -> dict[str, Any]:
    """Turn a valid self-signed request into an authority-signed identity record."""
    if not isinstance(request, dict) or request.get("kind") != "arbor-enrollment-request" or request.get("version") != 1:
        raise ValueError("invalid enrollment request")
    required = ("nodeId", "generation", "platform", "publicKey", "nonce", "signature")
    if any(field not in request for field in required):
        raise ValueError("incomplete enrollment request")
    try:
        VerifyKey(_unb64(request["publicKey"])).verify(
            canonical_json({key: value for key, value in request.items() if key != "signature"}),
            _unb64(request["signature"]),
        )
    except (ValueError, TypeError, binascii.Error, BadSignatureError) as error:
        raise ValueError("enrollment request signature is invalid") from error
    if not isinstance(request["nodeId"], str) or not isinstance(request["platform"], str):
        raise ValueError("enrollment request fields are invalid")
    if relationship_scope not in {"dependent", "independent"}:
        raise ValueError("relationship scope is invalid")
    payload = {
        "identity": request["nodeId"],
        "publicKey": request["publicKey"],
        "platform": request["platform"],
        "requestedParent": request.get("requestedParent"),
        "relationshipScope": relationship_scope,
        "enrollmentRequestDigest": _digest(request),
        "approvedBy": authority_key.issuer,
        "authorityRoot": authority_root or authority_key.issuer,
    }
    unsigned = {
        "protocolEpoch": 1,
        "wireVersion": 1,
        "schemaVersion": 1,
        "recordVersion": 1,
        "recordId": request["nodeId"],
        "generation": 1,
        "predecessor": None,
        "issuer": authority_key.issuer,
        "schema": "node-identity",
        "payload": payload,
    }
    return {**unsigned, "signature": authority_key.sign(unsigned)}


def make_lifecycle_record(
    issuer_key: RuntimeKey,
    schema: str,
    record_id: str,
    payload: dict[str, Any],
    *,
    generation: int = 1,
    predecessor: str | None = None,
    record_version: int = 1,
) -> dict[str, Any]:
    """Create a signed record in one of the accepted lifecycle families."""
    if schema not in {"enrollment", "identity-generation", "revocation", "recovery-authorization", "receipt"}:
        raise ValueError("schema is not a lifecycle family")
    if not isinstance(record_id, str) or not record_id or not isinstance(payload, dict):
        raise ValueError("record id and payload are required")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 1:
        raise ValueError("generation must be a positive integer")
    unsigned = {
        "protocolEpoch": 1, "wireVersion": 1, "schemaVersion": 1, "recordVersion": record_version,
        "recordId": record_id, "generation": generation, "predecessor": predecessor,
        "issuer": issuer_key.issuer, "schema": schema, "payload": payload,
    }
    return {**unsigned, "signature": issuer_key.sign(unsigned)}


def make_recovery_approval(
    approver_key: RuntimeKey,
    identity: str,
    lost_generation: int,
    *,
    role: str,
    approver_generation: int,
    operation: str = "recovery",
    decision: str = "approve",
) -> dict[str, Any]:
    """Create the signed, generation-bound approval used by recovery."""
    if (not isinstance(identity, str) or not identity or isinstance(lost_generation, bool)
            or not isinstance(lost_generation, int) or lost_generation < 1
            or role not in {"operator", "parent", "peer"}
            or isinstance(approver_generation, bool) or not isinstance(approver_generation, int)
            or approver_generation < 1 or operation != "recovery"
            or decision != "approve"):
        raise ValueError("invalid recovery approval")
    unsigned = {
        "approver": approver_key.issuer,
        "role": role,
        "subject": identity,
        "generation": lost_generation,
        "operation": operation,
        "approverGeneration": approver_generation,
        "decision": decision,
    }
    return {**unsigned, "issuer": approver_key.issuer, "signature": approver_key.sign(unsigned)}


def make_recovery_authorization(
    authority_key: RuntimeKey,
    identity: str,
    lost_generation: int,
    new_public_key: str,
    approvals: list[dict[str, Any]],
    *,
    provenance: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build an authority-signed recovery authorization transaction."""
    if not isinstance(new_public_key, str) or not isinstance(approvals, list) or not approvals:
        raise ValueError("recovery authorization is incomplete")
    payload = {
        "identity": identity,
        "lostGeneration": lost_generation,
        "newGeneration": lost_generation + 1,
        "newPublicKey": new_public_key,
        "approvals": approvals,
        "provenance": provenance or [],
    }
    unsigned = {
        "protocolEpoch": 1, "wireVersion": 1, "schemaVersion": 1, "recordVersion": 1,
        "recordId": f"{identity}:recovery:{lost_generation}", "generation": 1,
        "predecessor": None, "issuer": authority_key.issuer,
        "schema": "recovery-authorization", "payload": payload,
    }
    return {**unsigned, "signature": authority_key.sign(unsigned)}


def make_identity_generation(
    authority_key: RuntimeKey,
    identity: str,
    generation: int,
    public_key: str,
    *,
    predecessor: str | None = None,
    recovery_authorization: dict[str, Any] | None = None,
    provenance: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create an authority-approved active identity generation record."""
    if not isinstance(identity, str) or not identity or generation < 1 or not isinstance(public_key, str):
        raise ValueError("identity generation is invalid")
    authorization_digest = _digest(recovery_authorization) if recovery_authorization is not None else None
    payload = {
        "identity": identity, "generation": generation, "publicKey": public_key,
        "status": "active", "recoveryAuthorizationDigest": authorization_digest,
        "provenance": provenance if provenance is not None else (
            recovery_authorization.get("payload", {}).get("provenance", [])
            if recovery_authorization is not None else []
        ),
    }
    return make_lifecycle_record(
        authority_key, "identity-generation", identity, payload,
        generation=generation, predecessor=predecessor, record_version=generation,
    )


def make_revocation(
    authority_key: RuntimeKey,
    identity: str,
    generation: int,
    reason: str,
    *,
    provenance: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create an authority-signed revocation for one identity generation."""
    if not isinstance(identity, str) or generation < 1 or not isinstance(reason, str) or not reason:
        raise ValueError("revocation is invalid")
    return make_lifecycle_record(
        authority_key, "revocation", f"{identity}:revocation:{generation}",
        {"identity": identity, "generation": generation, "reason": reason, "provenance": provenance or []},
    )


def make_receipt(
    authority_key: RuntimeKey,
    subject: str,
    digest: str,
    *,
    provenance: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a signed receipt anchoring a lifecycle transaction."""
    if not isinstance(subject, str) or not subject or not isinstance(digest, str) or not digest:
        raise ValueError("receipt is invalid")
    return make_lifecycle_record(
        authority_key, "receipt", f"receipt:{subject}:{digest}",
        {"subject": subject, "digest": digest, "provenance": provenance or []},
    )


def generate_keypair(
    key_dir: Path,
    issuer: str,
    *,
    rotation: bool = False,
    generation: int | None = None,
) -> RuntimeKey:
    """Create runtime key material without silently replacing an identity.

    A generation writes ``<issuer>.g<generation>`` files, preserving older
    generations. Replacing the active ``<issuer>`` files requires the explicit
    ``rotation=True`` operation.
    """
    if (not isinstance(issuer, str) or not issuer or issuer in {".", ".."}
            or issuer != Path(issuer).name or "/" in issuer or "\\" in issuer or "\x00" in issuer):
        raise ValueError("issuer must be a single safe path component")
    if generation is not None and (isinstance(generation, bool) or not isinstance(generation, int) or generation < 1):
        raise ValueError("generation must be a positive integer")
    key_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = RuntimeKey(issuer, SigningKey.generate())
    suffix = f".g{generation}" if generation is not None else ""
    private_path = key_dir / f"{issuer}{suffix}.private"
    public_path = key_dir / f"{issuer}{suffix}.public"
    if not rotation and (private_path.exists() or public_path.exists()):
        raise FileExistsError(f"key material already exists for {issuer}{suffix}; use rotation=True or a new generation")
    # Replace only the explicitly selected generation, and do so atomically.
    # A crash must never leave a truncated private key that looks usable.
    for path, contents, mode in ((private_path, _b64(bytes(key.signing_key)), 0o600),
                                 (public_path, key.public_key + "\n", 0o600)):
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=key_dir)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise
    os.chmod(key_dir, 0o700)
    return key


def inspect_identity(key_dir: Path, issuer: str) -> dict[str, Any]:
    """Return non-secret identity metadata suitable for operator inspection."""
    key_dir = Path(key_dir)
    if not isinstance(issuer, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", issuer):
        raise ValueError("issuer is invalid")
    _secure_directory(key_dir)
    generations = []
    for path in sorted(key_dir.glob(f"{issuer}.g*.public")):
        match = re.fullmatch(re.escape(issuer) + r"\.g([1-9][0-9]*)\.public", path.name)
        if match is None:
            continue
        _secure_file(path)
        public = path.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", public):
            raise ValueError("identity public key is malformed")
        generation = int(match.group(1))
        generations.append({"generation": generation, "publicKey": public,
                            "privatePresent": (key_dir / f"{issuer}.g{generation}.private").exists()})
    active_public = key_dir / f"{issuer}.public"
    if active_public.exists():
        _secure_file(active_public)
        public = active_public.read_text(encoding="ascii").strip()
    else:
        public = generations[-1]["publicKey"] if generations else None
    return {"issuer": issuer, "activePublicKey": public,
            "generations": generations, "generationCount": len(generations)}


def rotate_identity(key_dir: Path, issuer: str, *, generation: int | None = None) -> RuntimeKey:
    """Explicitly create and publish the next identity generation."""
    metadata = inspect_identity(key_dir, issuer) if Path(key_dir).exists() else {"generations": []}
    current = max((item["generation"] for item in metadata["generations"]), default=0)
    target = generation if generation is not None else current + 1
    if target != current + 1:
        raise ValueError("identity rotation must advance exactly one generation")
    return generate_keypair(key_dir, issuer, generation=target, rotation=False)


def _age_run(args: list[str], *, input_bytes: bytes, timeout: float = 30.0) -> bytes:
    """Run age with secret data only on pipes; never include it in arguments."""
    try:
        result = subprocess.run([AGE_BINARY, *args], input=input_bytes, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("age recovery operation failed") from error
    if result.returncode != 0:
        raise ValueError("age recovery operation failed")
    return result.stdout


def export_recovery(key_dir: Path, issuer: str, destination: Path, *, recipient: str,
                    generation: int | None = None, runtime: "Runtime",
                    authorization: dict[str, Any]) -> dict[str, Any]:
    """Encrypt one private generation with age, atomically, and return a receipt."""
    if not isinstance(recipient, str) or not recipient.startswith("age1"):
        raise ValueError("recipient must be an age recipient")
    metadata = inspect_identity(key_dir, issuer)
    generation = generation or (max((x["generation"] for x in metadata["generations"]), default=0))
    if runtime._recovery_approval_reason(authorization.get("payload", {})) is not None:
        raise PermissionError("recovery authorization is not accepted")
    status, reason = runtime._validate(authorization)
    if status != "accepted" or reason is not None:
        raise PermissionError("recovery authorization is not accepted")
    if runtime.db.execute("SELECT status FROM records WHERE envelope = ?", (canonical_json(authorization).decode(),)).fetchone() != ("accepted",):
        raise PermissionError("recovery authorization is not durably accepted")
    payload = authorization.get("payload", {})
    if payload.get("identity") != issuer or payload.get("newGeneration") != generation:
        raise PermissionError("recovery authorization does not bind this identity generation")
    private = Path(key_dir) / f"{issuer}.g{generation}.private"
    _secure_file(private)
    if not private.exists():
        raise FileNotFoundError("requested identity generation is unavailable")
    expected_key = payload.get("newPublicKey")
    actual_key = metadata["generations"][-1]["publicKey"] if metadata["generations"] and generation == metadata["generations"][-1]["generation"] else None
    if expected_key != actual_key:
        raise PermissionError("recovery authorization key does not match generation")
    payload = {"format": "arbor-recovery-age-v1", "issuer": issuer, "generation": generation,
               "private": private.read_text(encoding="ascii").strip()}
    encrypted = _age_run(["-r", recipient], input_bytes=canonical_json(payload))
    if len(encrypted) > MAX_RECOVERY_BYTES:
        raise ValueError("recovery archive exceeds size limit")
    destination = Path(destination)
    _secure_directory(destination.parent)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(encrypted); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    digest = hashlib.sha256(encrypted).hexdigest()
    manifest = {"format": "arbor-recovery-manifest-v1", "issuer": issuer,
                "generation": generation, "ciphertextSha256": digest,
                "recipient": recipient,
                "authorizationDigest": _digest(authorization) if authorization is not None else None,
                "provenance": "manual-private-recovery"}
    manifest_path = destination.with_name(destination.name + ".manifest.json")
    fd, temporary = tempfile.mkstemp(prefix=f".{manifest_path.name}.", dir=manifest_path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical_json(manifest) + b"\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, manifest_path)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise
    return {"issuer": issuer, "generation": generation, "digest": digest,
            "manifest": str(manifest_path.name)}


def import_recovery(archive: Path, key_dir: Path, *, identity_file: Path,
                    expected_issuer: str | None = None, expected_generation: int | None = None,
                    runtime: "Runtime", authorization: dict[str, Any], expected_recipient: str | None = None) -> RuntimeKey:
    """Decrypt and install an age recovery generation without overwriting one."""
    _secure_file(Path(archive)); _secure_file(Path(identity_file))
    if Path(archive).stat().st_size > MAX_RECOVERY_BYTES:
        raise ValueError("recovery archive exceeds size limit")
    manifest_path = Path(archive).with_name(Path(archive).name + ".manifest.json")
    _secure_file(manifest_path)
    if not manifest_path.exists():
        raise ValueError("recovery manifest is missing")
    try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("malformed recovery manifest") from error
    digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    if manifest.get("format") != "arbor-recovery-manifest-v1" or manifest.get("ciphertextSha256") != digest:
        raise ValueError("recovery manifest does not match ciphertext")
    if expected_recipient is not None and manifest.get("recipient") != expected_recipient:
        raise PermissionError("recovery recipient mismatch")
    plaintext = _age_run(["-d", "-i", str(identity_file), str(archive)], input_bytes=b"")
    try: payload = json.loads(plaintext)
    except (UnicodeDecodeError, json.JSONDecodeError) as error: raise ValueError("malformed recovery archive") from error
    if (not isinstance(payload, dict) or payload.get("format") != "arbor-recovery-age-v1"
            or not isinstance(payload.get("issuer"), str)
            or not isinstance(payload.get("generation"), int) or not isinstance(payload.get("private"), str)):
        raise ValueError("recovery sentinel or archive metadata mismatch")
    issuer, generation = payload["issuer"], payload["generation"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", issuer):
        raise ValueError("recovery issuer is invalid")
    if expected_issuer is not None and issuer != expected_issuer: raise ValueError("recovery issuer mismatch")
    if expected_generation is not None and generation != expected_generation: raise ValueError("recovery generation mismatch")
    if runtime._recovery_approval_reason(authorization.get("payload", {})) is not None:
        raise PermissionError("recovery authorization is not accepted")
    status, reason = runtime._validate(authorization)
    if status != "accepted" or reason is not None:
        raise PermissionError("recovery authorization is not accepted")
    if runtime.db.execute("SELECT status FROM records WHERE envelope = ?", (canonical_json(authorization).decode(),)).fetchone() != ("accepted",):
        raise PermissionError("recovery authorization is not durably accepted")
    auth_payload = authorization.get("payload", {})
    if auth_payload.get("identity") != issuer or auth_payload.get("newGeneration") != generation:
        raise PermissionError("recovery authorization does not bind this identity generation")
    if manifest.get("authorizationDigest") != _digest(authorization):
        raise PermissionError("recovery manifest authorization mismatch")
    current = runtime.projection().get(issuer, {}).get("generation", 0)
    rows = runtime.db.execute("SELECT envelope FROM records WHERE status = 'accepted' AND record_id = ?", (issuer,)).fetchall()
    current = max([current] + [json.loads(row[0]).get("generation", 0) for row in rows])
    revoked = runtime.db.execute("SELECT 1 FROM records WHERE status = 'accepted' AND envelope LIKE ?", (f'%"identity":"{issuer}"%',)).fetchone()
    revoked = any(json.loads(row[0]).get("schema") == "revocation"
                  and json.loads(row[0]).get("payload", {}).get("identity") == issuer
                  and json.loads(row[0]).get("payload", {}).get("generation") == generation
                  for row in runtime.db.execute("SELECT envelope FROM records WHERE status = 'accepted'"))
    if revoked:
        raise PermissionError("recovery generation is revoked")
    if isinstance(current, int) and generation <= current:
        raise PermissionError("recovery generation is stale or already installed")
    try: signing = SigningKey(_unb64(payload["private"]))
    except (ValueError, TypeError, binascii.Error) as error: raise ValueError("recovery key is malformed") from error
    if auth_payload.get("newPublicKey") != _b64(bytes(signing.verify_key)):
        raise PermissionError("recovery authorization key does not match recovered key")
    destination = Path(key_dir); _secure_directory(destination)
    private, public = destination / f"{issuer}.g{generation}.private", destination / f"{issuer}.g{generation}.public"
    if private.exists() or public.exists(): raise FileExistsError("recovery generation already exists")
    for path, contents, mode in ((private, _b64(bytes(signing)), 0o600),
                                 (public, _b64(bytes(signing.verify_key)) + "\n", 0o600)):
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=destination)
        try:
            os.fchmod(fd, mode)
            with os.fdopen(fd, "w", encoding="ascii") as stream:
                stream.write(contents); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            try: os.unlink(temporary)
            except FileNotFoundError: pass
            raise
    return RuntimeKey(issuer, signing)


def inspect_recovery_data(path: Path) -> dict[str, Any]:
    """Classify a private recovery artifact without reading secret contents."""
    path = Path(path)
    _secure_file(path)
    if not path.exists():
        raise FileNotFoundError(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"kind": "private-recovery-data", "path": path.name, "bytes": path.stat().st_size,
            "sha256": digest, "provenance": {"source": "manual-private-recovery"}}


def inventory_recovery_catalog(root: Path, *, selected: Iterable[str] | None = None) -> dict[str, Any]:
    """Validate a checked-out private catalog and return redacted inventory only."""
    root = Path(root); _secure_directory(root)
    catalog_path, schema_path = root / "catalog.yaml", root / "schema.yaml"
    if not catalog_path.exists() or not schema_path.exists():
        raise ValueError("private recovery catalog requires catalog.yaml and schema.yaml")
    names = set(selected) if selected is not None else None
    entries = []
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*-?\s*(?:path|material):\s*([^#\s]+)", line)
        if match and (names is None or match.group(1) in names):
            rel = Path(match.group(1))
            if rel.is_absolute() or ".." in rel.parts: raise ValueError("catalog path escapes root")
            target = root / rel
            _secure_file(target)
            if not target.exists(): raise FileNotFoundError(rel)
            entries.append({"name": rel.name, "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    return {"kind": "private-recovery-catalog", "entries": entries,
            "provenance": {"source": "manual-private-recovery", "selected": selected is not None}}


# Descriptive aliases retained for callers that use “bundle” terminology.
export_recovery_bundle = export_recovery
import_recovery_bundle = import_recovery
import_private_recovery_data = import_recovery
inspect_private_recovery_data = inspect_recovery_data
inspect_identity_state = inspect_identity
rotate_keypair = rotate_identity


class Provider(ABC):
    """Append-only raw transport contract used by :class:`Runtime`.

    Providers are deliberately transport-only.  ``append`` must durably
    retain the exact record and may return its zero-based cursor.  Repeating
    the same record must return the original cursor; a different record with
    the same logical key remains a transport entry for the runtime to
    quarantine.  ``fetch`` returns ``(cursor, record)`` pairs in strictly
    increasing cursor order and must enforce its own bounded page size.

    Validation, authority, reconciliation, and materialization stay in
    ``Runtime`` so an external provider cannot grant trust by accepting a
    record.  A network adapter can implement this contract later without
    becoming part of Nix evaluation.
    """

    @abstractmethod
    def append(self, record: dict[str, Any]) -> ProviderCursor: ...

    @abstractmethod
    def fetch(self, cursor: ProviderCursor = 0, limit: int = 100) -> list[tuple[ProviderCursor, dict[str, Any]]]: ...


class FileProvider(Provider):
    """Append-only JSONL transport. Cursors are line offsets, never timestamps."""

    def __init__(self, raw_path: Path):
        self.raw_path = Path(raw_path)
        _secure_directory(self.raw_path.parent)
        _secure_file(self.raw_path)

    def append(self, record: dict[str, Any]) -> int:
        lock_path = self.raw_path.with_name(self.raw_path.name + ".lock")
        with lock_path.open("a+") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                cursor = 0
                while True:
                    batch = self.fetch(cursor, 1000)
                    for offset, item in batch:
                        if _key(item) == _key(record) and item == record:
                            return offset
                    if len(batch) < 1000:
                        break
                    cursor += len(batch)
                if self.raw_path.exists():
                    with self.raw_path.open(encoding="utf-8") as stream:
                        cursor = sum(1 for _ in stream)
                else:
                    cursor = 0
                with self.raw_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                return cursor
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def fetch(self, cursor: int = 0, limit: int = 100) -> list[tuple[int, dict[str, Any]]]:
        if cursor < 0 or limit < 1 or limit > 1000:
            raise ValueError("cursor must be non-negative and limit must be between 1 and 1000")
        if not self.raw_path.exists():
            return []
        result = []
        with self.raw_path.open(encoding="utf-8") as stream:
            for offset, line in enumerate(stream):
                if offset >= cursor and len(result) < limit:
                    result.append((offset, json.loads(line)))
        return result


class OrbitDBProvider(Provider):
    """Runtime-only adapter for the reference registryd Unix-socket contract.

    OrbitDB/Helia remain transport concerns. Validation, authority, receipts,
    and reconciliation stay in ``Runtime`` or the external controller.
    """

    def __init__(self, socket_path: Path, stream: str, *, token: str | None = None,
                 timeout: float = 30.0,
                 encode: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
                 decode: Callable[[dict[str, Any]], dict[str, Any]] | None = None):
        if not isinstance(stream, str) or not stream or len(stream) > 64:
            raise ValueError("stream must be a non-empty string of at most 64 characters")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.socket_path = Path(socket_path)
        self.stream = stream
        self.token = token
        self.timeout = timeout
        self.encode = encode or (lambda record: record)
        self.decode = decode or (lambda record: record)
        self.next_cursor: ProviderCursor | None = None

    def _request(self, request: dict[str, Any]) -> dict[str, Any]:
        request = dict(request)
        if self.token is not None:
            request["token"] = self.token
        payload = (json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        deadline = time.monotonic() + self.timeout
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            connection.connect(str(self.socket_path))
            try:
                connection.sendall(payload)
            except OSError as error:
                raise ValueError("OrbitDB provider connection failed") from error
            response = bytearray()
            while not response.endswith(b"\n"):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("OrbitDB provider request timed out")
                connection.settimeout(remaining)
                chunk = connection.recv(65536)
                if not chunk:
                    break
                response.extend(chunk)
                if len(response) > 1024 * 1024:
                    raise ValueError("OrbitDB provider response exceeds 1 MiB")
        try:
            value = json.loads(response.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("OrbitDB provider returned malformed JSON") from error
        if not isinstance(value, dict) or value.get("ok") is not True:
            error = value.get("error") if isinstance(value, dict) else None
            code = error.get("code") if isinstance(error, dict) else "transport_error"
            raise RuntimeError(f"OrbitDB provider request failed: {code}")
        return value

    def append(self, record: dict[str, Any]) -> ProviderCursor:
        response = self._request({"operation": "append", "stream": self.stream, "event": self.encode(record)})
        result = response.get("cursor")
        if not isinstance(result, str) or not re.fullmatch(r"(?:v1:(0|[1-9][0-9]*)|v2(?:-after)?:[A-Za-z0-9._:-]{1,1024})", result):
            raise ValueError("OrbitDB provider append response has no valid cursor")
        return result

    def fetch(self, cursor: ProviderCursor = 0, limit: int = 100) -> list[tuple[ProviderCursor, dict[str, Any]]]:
        if isinstance(cursor, int):
            if cursor < 0:
                raise ValueError("cursor must be non-negative")
            cursor = f"v1:{cursor}"
        elif not isinstance(cursor, str):
            raise ValueError("cursor must be an integer or opaque string")
        elif not cursor or len(cursor) > 1024:
            raise ValueError("cursor must be a non-empty bounded string")
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        response = self._request({"operation": "list", "stream": self.stream, "limit": limit, "cursor": cursor})
        records = response.get("records")
        if not isinstance(records, list):
            raise ValueError("OrbitDB provider list response has no records")
        next_cursor = response.get("nextCursor")
        if not isinstance(next_cursor, str) or not next_cursor or len(next_cursor) > 1024:
            raise ValueError("OrbitDB provider list response has no next cursor")
        if next_cursor.startswith("v1:") and re.fullmatch(r"v1:(0|[1-9][0-9]*)", next_cursor) is None:
            raise ValueError("OrbitDB provider list response has malformed next cursor")
        self.next_cursor = next_cursor
        result = []
        previous_sequence: int | None = None
        requested_sequence = int(cursor[3:]) if re.fullmatch(r"v1:(0|[1-9][0-9]*)", cursor) else None
        for item in records:
            if not isinstance(item, dict) or not isinstance(item.get("hash"), str) or not isinstance(item.get("event"), dict):
                raise ValueError("OrbitDB provider list response contains a malformed record")
            cursor = item.get("sequence", item["hash"])
            if not isinstance(cursor, (int, str)) or isinstance(cursor, bool):
                raise ValueError("OrbitDB provider list response contains a malformed cursor")
            if isinstance(cursor, int):
                if cursor < 0 or (requested_sequence is not None and cursor < requested_sequence):
                    raise ValueError("OrbitDB provider list response contains an out-of-range cursor")
                if previous_sequence is not None and cursor <= previous_sequence:
                    raise ValueError("OrbitDB provider list response cursors are not strictly increasing")
                previous_sequence = cursor
            elif not cursor or len(cursor) > 1024:
                raise ValueError("OrbitDB provider list response contains an invalid opaque cursor")
            result.append((cursor, self.decode(item["event"])))
        if previous_sequence is not None and next_cursor.startswith("v1:") and int(next_cursor[3:]) <= previous_sequence:
            raise ValueError("OrbitDB provider list response next cursor does not advance")
        return result


class Runtime:
    """Ingest envelopes, retain quarantine, and rebuild a deterministic projection."""

    def __init__(
        self,
        state_dir: Path,
        provider: Provider,
        public_keys: dict[str, str],
        max_bytes: int = 131072,
        *,
        authority_issuers: set[str] | None = None,
        approver_roles: dict[str, set[str]] | None = None,
        recovery_thresholds: dict[str, int] | None = None,
    ):
        self.state_dir = Path(state_dir)
        _secure_directory(self.state_dir)
        self.provider = provider
        self.public_keys = dict(public_keys)
        self.authority_issuers = set(authority_issuers) if authority_issuers is not None else (
            {"root"} if "root" in self.public_keys else set()
        )
        self.approver_roles = approver_roles or {"operator": set(self.authority_issuers), "parent": set(), "peer": set()}
        self.recovery_thresholds = recovery_thresholds or {"operator": 1, "parent": 0, "peer": 0}
        if not self.authority_issuers.issubset(self.public_keys):
            raise ValueError("authority issuers must have configured public keys")
        self.max_bytes = max_bytes
        self.max_quarantine_records = 10000
        database_path = self.state_dir / "registry.sqlite3"
        self.db = sqlite3.connect(database_path, timeout=30)
        if database_path.exists():
            os.chmod(database_path, 0o600)
        _secure_file(self.state_dir / "registry.sqlite3")
        self.db.execute("PRAGMA busy_timeout = 30000")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS records (
            record_key TEXT PRIMARY KEY, record_id TEXT, generation INTEGER,
            predecessor TEXT, status TEXT NOT NULL, reason TEXT, envelope TEXT NOT NULL
          );
          CREATE TABLE IF NOT EXISTS projection (
            record_id TEXT PRIMARY KEY, schema TEXT NOT NULL, payload TEXT NOT NULL, generation INTEGER NOT NULL
          );
        """)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def _validate(self, record: dict[str, Any]) -> tuple[str, str | None]:
        if isinstance(record, dict) and record.get("quarantined") is True and record.get("reason") == "unsafe-value":
            return "quarantined", "unsafe-value"
        required = ("protocolEpoch", "wireVersion", "schemaVersion", "recordId", "recordVersion",
                    "generation", "predecessor", "schema", "payload", "issuer", "signature")
        if not isinstance(record, dict) or any(name not in record for name in required):
            return "quarantined", "malformed-record"
        integer_fields = ("protocolEpoch", "wireVersion", "schemaVersion", "recordVersion", "generation")
        if any(isinstance(record[name], bool) or not isinstance(record[name], int) for name in integer_fields):
            return "quarantined", "malformed-record"
        if (not isinstance(record["recordId"], str) or not isinstance(record["schema"], str)
                or not isinstance(record["payload"], dict) or record["generation"] < 1
                or not isinstance(record["predecessor"], (str, type(None)))
                or not isinstance(record["issuer"], str) or not isinstance(record["signature"], str)):
            return "quarantined", "malformed-record"
        if record["schema"] not in SCHEMAS:
            return "quarantined", "unknown-schema" if record.get("schema") not in SCHEMAS else "malformed-record"
        if record["schemaVersion"] != 1:
            return "quarantined", "unsupported-schema-version"
        if record["protocolEpoch"] != 1:
            return "quarantined", "unknown-epoch"
        if record["wireVersion"] != 1:
            return "quarantined", "unsupported-wire-version"
        features = record.get("requiredFeatures", [])
        if (not isinstance(features, list) or any(not isinstance(feature, str) for feature in features)):
            return "quarantined", "malformed-record"
        if features:
            return "quarantined", "unsupported-required-feature"
        try:
            encoded = canonical_json(record)
            unsigned = canonical_json(_without_signature(record))
        except (TypeError, ValueError):
            return "quarantined", "malformed-record"
        if len(encoded) > self.max_bytes:
            return "quarantined", "framing-limit"
        if _unsafe_value(_without_signature(record)):
            return "quarantined", "unsafe-value"
        try:
            verify = VerifyKey(_unb64(self.public_keys[record["issuer"]]))
            verify.verify(unsigned, _unb64(record["signature"]))
        except (KeyError, ValueError, TypeError, binascii.Error, BadSignatureError):
            return "quarantined", "invalid-signature"
        payload = record["payload"]
        sensitive_schemas = {
            "node-identity", "identity-generation", "enrollment", "revocation",
            "recovery-authorization", "receipt", "relationship", "capability",
        }
        if record["schema"] in sensitive_schemas and record["issuer"] not in self.authority_issuers:
            return "quarantined", "unauthorized-authority"
        authority_root = payload.get("authorityRoot")
        if authority_root is not None and authority_root not in self.authority_issuers:
            return "quarantined", "unauthorized-authority-root"
        if record["schema"] == "enrollment":
            if (not isinstance(payload.get("identity"), str) or not isinstance(payload.get("publicKey"), str)
                    or not isinstance(payload.get("requestDigest"), str)
                    or payload.get("approvedBy") != record["issuer"]):
                return "quarantined", "unapproved-enrollment"
        if record["schema"] == "identity-generation":
            if (not isinstance(payload.get("identity"), str) or not isinstance(payload.get("publicKey"), str)
                    or payload.get("generation") != record["generation"]
                    or payload.get("status", "active") not in {"active", "deprecated"}):
                return "quarantined", "malformed-identity-generation"
        if record["schema"] == "revocation":
            if (not isinstance(payload.get("identity"), str) or not isinstance(payload.get("generation"), int)
                    or payload["generation"] < 1 or not isinstance(payload.get("reason"), str)
                    or not payload["reason"]):
                return "quarantined", "malformed-revocation"
        if record["schema"] == "recovery-authorization":
            if self._recovery_approval_reason(payload) is not None:
                return "quarantined", self._recovery_approval_reason(payload)
        if record["schema"] == "receipt":
            if not isinstance(payload.get("subject"), str) or not isinstance(payload.get("digest"), str):
                return "quarantined", "malformed-receipt"
        return "accepted", None

    def _recovery_approval_reason(self, payload: dict[str, Any]) -> str | None:
        identity = payload.get("identity")
        lost = payload.get("lostGeneration")
        new = payload.get("newGeneration")
        approvals = payload.get("approvals")
        if (not isinstance(identity, str) or not isinstance(lost, int) or isinstance(lost, bool) or lost < 1
                or new != lost + 1 or not isinstance(payload.get("newPublicKey"), str)
                or not isinstance(approvals, list) or not approvals
                or not isinstance(payload.get("provenance", []), list)):
            return "malformed-recovery-authorization"
        seen: set[tuple[str, str]] = set()
        counts = {role: 0 for role in ("operator", "parent", "peer")}
        for approval in approvals:
            if not isinstance(approval, dict) or any(key not in approval for key in (
                    "approver", "role", "subject", "generation", "operation", "approverGeneration", "decision", "signature")):
                return "invalid-recovery-approval"
            if approval.get("subject") != identity or approval.get("generation") != lost:
                return "unbound-recovery-approval"
            if (approval["subject"] != identity or approval["generation"] != lost
                    or approval["operation"] != "recovery" or approval["decision"] != "approve"
                    or approval["role"] not in {"operator", "parent", "peer"}
                    or not isinstance(approval["approverGeneration"], int)
                    or approval["approverGeneration"] < 1
                    or approval.get("approver") != approval.get("issuer")):
                return "unbound-recovery-approval"
            approver = approval["approver"]
            role = approval["role"]
            if approver not in self.approver_roles.get(role, set()):
                return "untrusted-recovery-approver"
            identity_key = (approver, role)
            if identity_key in seen:
                return "duplicate-recovery-approver"
            seen.add(identity_key)
            counts[role] += 1
            try:
                key = VerifyKey(_unb64(self.public_keys[approval["approver"]]))
                unsigned = {key: value for key, value in approval.items() if key not in {"signature", "issuer"}}
                key.verify(canonical_json(unsigned), _unb64(approval["signature"]))
            except (KeyError, ValueError, TypeError, binascii.Error, BadSignatureError):
                return "invalid-recovery-approval-signature"
        if any(counts[role] < threshold for role, threshold in self.recovery_thresholds.items()):
            return "recovery-quorum-not-met"
        return None

    def ingest(self, records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        outcomes = []
        for record in records:
            if isinstance(record, dict) and "recordId" in record and "recordVersion" in record:
                record_key = _key(record)
            else:
                try:
                    record_key = "malformed:" + _digest(record)
                except (TypeError, ValueError):
                    record_key = "malformed:unserializable"
            status, reason = self._validate(record)
            unsafe = _unsafe_value(_without_signature(record)) if isinstance(record, dict) else False
            if unsafe:
                envelope = json.dumps({
                    "quarantined": True, "reason": "unsafe-value",
                    "recordId": record.get("recordId") if isinstance(record, dict) else None,
                    "recordVersion": record.get("recordVersion") if isinstance(record, dict) else None,
                }, sort_keys=True)
            else:
                try:
                    envelope = canonical_json(record).decode()
                except (TypeError, ValueError):
                    envelope = json.dumps({"malformed": "unserializable-record"}, sort_keys=True)
            exact = self.db.execute("SELECT record_key, status FROM records WHERE envelope = ?", (envelope,)).fetchone()
            existing = self.db.execute("SELECT envelope, status FROM records WHERE record_key = ?", (record_key,)).fetchone()
            if exact:
                record_key = exact[0]
                status, reason = exact[1], None
            else:
                if existing:
                    record_key = f"{record_key}#conflict:{hashlib.sha256(envelope.encode()).hexdigest()}"
                if not unsafe:
                    self.provider.append(record)
                self.db.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (record_key, record.get("recordId"), record.get("generation"), record.get("predecessor"),
                     status, reason, envelope))
            outcomes.append({"recordKey": record_key, "status": status, "reason": reason})
        self.db.execute("DELETE FROM records WHERE status = 'quarantined' AND rowid NOT IN (SELECT rowid FROM records WHERE status = 'quarantined' ORDER BY rowid DESC LIMIT ?)", (self.max_quarantine_records,))
        self.db.commit()
        self._reconcile()
        self._materialize()
        for outcome in outcomes:
            row = self.db.execute("SELECT status, reason FROM records WHERE record_key = ?", (outcome["recordKey"],)).fetchone()
            if row:
                outcome["status"], outcome["reason"] = row
        return outcomes

    def _reconcile(self) -> None:
        rows = self.db.execute("SELECT rowid, record_key, record_id, generation, predecessor, envelope FROM records").fetchall()
        records = [(rowid, record_key, json.loads(raw)) for rowid, record_key, _, _, _, raw in rows]
        by_key: dict[str, list[tuple[int, str, dict[str, Any]]]] = {}
        for rowid, record_key, record in records:
            base_key = _key(record) if isinstance(record, dict) else record_key
            by_key.setdefault(base_key, []).append((rowid, record_key, record))
        reasons: dict[int, str | None] = {}
        valid = []
        for rowid, record_key, record in records:
            status, reason = self._validate(record)
            reasons[rowid] = reason
            if status == "accepted":
                valid.append((rowid, record_key, record))
        for entries in by_key.values():
            valid_entries = [item for item in entries if reasons[item[0]] is None]
            if len({canonical_json(item[2]) for item in valid_entries}) > 1:
                for rowid, _, _ in entries:
                    if reasons[rowid] is None:
                        reasons[rowid] = "conflicting-record-key"
        candidates = [entry for entry in valid if reasons[entry[0]] is None]
        # Lifecycle records form a small, signed state machine layered over
        # ordinary lineage.  A revocation is authoritative for every record
        # carrying the same identity/generation, including materialization.
        revocations = {
            (record["payload"]["identity"], record["payload"]["generation"])
            for _, _, record in candidates
            if record["schema"] == "revocation"
            and isinstance(record.get("payload"), dict)
            and isinstance(record["payload"].get("identity"), str)
            and isinstance(record["payload"].get("generation"), int)
        }
        authorizations = {
            (record["payload"]["identity"], record["payload"]["newGeneration"]): record
            for _, _, record in candidates
            if record["schema"] == "recovery-authorization"
            and isinstance(record.get("payload"), dict)
            and isinstance(record["payload"].get("identity"), str)
            and isinstance(record["payload"].get("newGeneration"), int)
        }
        active_generations: dict[str, int] = {}
        for _, _, record in candidates:
            payload = record.get("payload", {})
            if (record["schema"] == "identity-generation" and isinstance(payload, dict)
                    and isinstance(payload.get("identity"), str)
                    and isinstance(payload.get("generation"), int)
                    and payload.get("status", "active") == "active"):
                identity = payload["identity"]
                active_generations[identity] = max(active_generations.get(identity, 0), payload["generation"])
        for rowid, _, record in candidates:
            if record["schema"] != "recovery-authorization" or reasons[rowid] is not None:
                continue
            for approval in record.get("payload", {}).get("approvals", []):
                approver = approval.get("approver") if isinstance(approval, dict) else None
                generation = approval.get("approverGeneration") if isinstance(approval, dict) else None
                if approver not in self.authority_issuers and active_generations.get(approver) != generation:
                    reasons[rowid] = "stale-approver-generation"
                    break
        for rowid, _, record in candidates:
            payload = record.get("payload", {})
            identity = payload.get("identity") if isinstance(payload, dict) else None
            generation = payload.get("generation") if isinstance(payload, dict) else None
            if (identity, generation) in revocations and record["schema"] != "revocation":
                reasons[rowid] = "revoked-generation"
            if record["schema"] == "identity-generation":
                if payload.get("status", "active") != "active":
                    reasons[rowid] = "inactive-generation"
                if (identity, generation) in revocations:
                    reasons[rowid] = "revoked-generation"
            if record["schema"] == "node-identity" and isinstance(payload, dict):
                if payload.get("identityGeneration") is not None and (
                        identity, payload.get("identityGeneration")) in revocations:
                    reasons[rowid] = "revoked-generation"
            record_generation = payload.get("identityGeneration") if record["schema"] == "node-identity" else generation
            if isinstance(identity, str) and isinstance(record_generation, int) and identity in active_generations:
                if (reasons[rowid] is None and record_generation < active_generations[identity]
                        and record["schema"] not in {"revocation", "recovery-authorization"}):
                    reasons[rowid] = "stale-generation"
            if record["schema"] == "identity-generation" and generation > 1:
                authorization = authorizations.get((identity, generation))
                if authorization is None or authorization["payload"].get("lostGeneration") != generation - 1:
                    reasons[rowid] = "missing-recovery-authorization"
                else:
                    payload_digest = payload.get("recoveryAuthorizationDigest")
                    if payload_digest != _digest(authorization):
                        reasons[rowid] = "recovery-provenance-mismatch"
        by_id: dict[str, list[dict[str, Any]]] = {}
        for _, _, record in candidates:
            by_id.setdefault(record["recordId"], []).append(record)
        max_generation = {record_id: max(item["generation"] for item in items) for record_id, items in by_id.items()}
        for rowid, _, record in candidates:
            if reasons[rowid] is None and record["generation"] < max_generation[record["recordId"]]:
                reasons[rowid] = "anti-rollback"
        successors: dict[str, set[tuple[str, int]]] = {}
        for _, _, record in candidates:
            if record["predecessor"] is not None:
                successors.setdefault(record["predecessor"], set()).add((record["recordId"], record["generation"]))
        for rowid, _, record in candidates:
            if record["predecessor"] is not None and len(successors.get(record["predecessor"], set())) > 1:
                reasons[rowid] = "forked-lineage"
        # Historical predecessors remain usable for continuity even when they
        # are no longer current state (anti-rollback). They are not exposed as
        # accepted records or projected state below.
        available = {
            alias
            for rowid, _, record in candidates
            if reasons[rowid] not in {"conflicting-record-key", "forked-lineage"}
            for alias in ((record["recordId"], record["generation"]),
                          (f"{record['recordId']}:{record['generation']}", record["generation"]))
        }
        for rowid, _, record in candidates:
            if reasons[rowid] is not None:
                continue
            if record["schema"] in {"enrollment", "revocation", "recovery-authorization", "receipt"}:
                continue
            predecessor = record["predecessor"]
            if not ((record["generation"] == 1 and predecessor is None)
                    or (predecessor, record["generation"] - 1) in available):
                reasons[rowid] = "missing-predecessor"
        with self.db:
            for rowid, _, _, _, _, _ in rows:
                status = "accepted" if reasons[rowid] is None else "quarantined"
                self.db.execute("UPDATE records SET status = ?, reason = ? WHERE rowid = ?", (status, reasons[rowid], rowid))

    def _materialize(self) -> None:
        accepted = self.db.execute("SELECT record_key, record_id, generation, predecessor, status, reason, envelope FROM records WHERE status = 'accepted' OR reason IN ('anti-rollback', 'revoked-generation') ORDER BY generation, record_key").fetchall()
        available: dict[str, dict[str, Any]] = {}
        available_ids: set[str] = set()
        accepted_keys = {record_key for record_key, _, _, _, status, _, _ in accepted if status == "accepted"}
        for record_key, record_id, generation, predecessor, _, _, raw in accepted:
            if (generation == 1 and predecessor is None) or predecessor in available_ids:
                record = json.loads(raw)
                available[_key(record)] = record
                available_ids.add(record["recordId"])
                available_ids.add(f"{record['recordId']}:{record['generation']}")
        latest: dict[str, tuple[int, dict[str, Any]]] = {}
        for record in available.values():
            if _key(record) not in accepted_keys:
                continue
            if record["schema"] in {"enrollment", "revocation", "recovery-authorization", "receipt"}:
                continue
            current = latest.get(record["recordId"])
            if current is None or record["generation"] >= current[0]:
                latest[record["recordId"]] = (record["generation"], record)
        with self.db:
            self.db.execute("DELETE FROM projection")
            self.db.executemany("INSERT INTO projection VALUES (?, ?, ?, ?)",
                [(record_id, record["schema"], json.dumps(record["payload"], sort_keys=True), generation)
                 for record_id, (generation, record) in latest.items()])

    def accepted(self, cursor: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1 or limit > 1000 or cursor < 0:
            raise ValueError("cursor must be non-negative and limit must be between 1 and 1000")
        rows = self.db.execute("SELECT envelope FROM records WHERE status = 'accepted' ORDER BY rowid LIMIT ? OFFSET ?", (limit, cursor)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def quarantine(self) -> list[dict[str, Any]]:
        return [{"record": json.loads(raw), "reason": reason} for raw, reason in self.db.execute("SELECT envelope, reason FROM records WHERE status = 'quarantined' ORDER BY rowid")]

    def projection(self) -> dict[str, dict[str, Any]]:
        return {record_id: {"schema": schema, "payload": json.loads(payload), "generation": generation}
                for record_id, schema, payload, generation in self.db.execute("SELECT record_id, schema, payload, generation FROM projection")}
