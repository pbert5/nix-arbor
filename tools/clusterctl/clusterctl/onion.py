import base64
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from .canonical import canonical_sha256
from .events import now_utc, read_json, write_json
from .registry import cluster_id
from .signing import key_fingerprint, sign_record, verify_signature


HEAD_SCHEMA = "cluster.identity.onion-head.v1"
TOR_V3_PUBLIC_KEY_HEADER = b"== ed25519v1-public: type0 ==\0\0\0"
TOR_V3_VERSION = b"\x03"


def _config(policy: dict) -> dict:
    return ((policy.get("registry") or {}).get("onion") or {})


def enabled(policy: dict) -> bool:
    transports = ((policy.get("registry") or {}).get("transports") or {})
    return bool(transports.get("onionMirrors", False))


def mirror_path(policy: dict) -> Path:
    configured = _config(policy).get("mirrorPath")
    return Path(configured or "/var/lib/cluster-identity/onion-mirror")


def derive_onion_address_from_public_key_file(public_key_file_base64: str) -> str:
    raw = base64.b64decode(public_key_file_base64, validate=True)
    if len(raw) != 64 or not raw.startswith(TOR_V3_PUBLIC_KEY_HEADER):
        raise ValueError("Tor v3 public key file has an unexpected format")
    public_key = raw[-32:]
    checksum = hashlib.sha3_256(
        b".onion checksum" + public_key + TOR_V3_VERSION
    ).digest()[:2]
    return (
        base64.b32encode(public_key + checksum + TOR_V3_VERSION)
        .decode("ascii")
        .lower()
        .rstrip("=")
        + ".onion"
    )


def _base_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname is None
        or not parsed.hostname.endswith(".onion")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("onion mirror must be an http://*.onion URL")
    return value.rstrip("/")


def build_head(
    policy: dict,
    publisher_state: dict,
    root: dict,
    signing_key: Path,
) -> dict:
    leader = publisher_state.get("publisher")
    trusted = (policy.get("trustedLeaders") or {}).get(leader) or {}
    public_key = trusted.get("publicSigningKey")
    onion_mirror = trusted.get("onionMirror")
    if not public_key or not onion_mirror:
        raise ValueError(f"publisher {leader!r} has no enrolled onion mirror")
    if root.get("publisher") != leader:
        raise ValueError("published root does not match the onion mirror leader")
    if publisher_state.get("rootSequence") != root.get("rootSequence"):
        raise ValueError("publisher state does not match the mirrored root")

    head = {
        "schema": HEAD_SCHEMA,
        "clusterId": cluster_id(policy),
        "leader": leader,
        "leaderKeyId": key_fingerprint(public_key),
        "onionMirror": _base_url(onion_mirror),
        "onionServicePublicKey": trusted.get("onionServicePublicKey"),
        "rootCid": publisher_state.get("rootCid"),
        "rootSequence": publisher_state.get("rootSequence"),
        "previousRootCid": publisher_state.get("previousRootCid"),
        "rootDigest": canonical_sha256(root),
        "createdAt": now_utc(),
    }
    head["signature"] = sign_record(head, signing_key)
    return head


def validate_head(policy: dict, leader: str, head: dict) -> dict:
    trusted = (policy.get("trustedLeaders") or {}).get(leader) or {}
    expected_mirror = trusted.get("onionMirror")
    if not isinstance(head, dict) or head.get("schema") != HEAD_SCHEMA:
        raise ValueError("unsupported onion mirror head schema")
    if head.get("clusterId") != cluster_id(policy):
        raise ValueError("onion mirror head is for another cluster")
    if head.get("leader") != leader:
        raise ValueError("onion mirror head has the wrong leader")
    if head.get("onionMirror") != _base_url(expected_mirror):
        raise ValueError("onion mirror head does not match trusted policy")
    if head.get("onionServicePublicKey") != trusted.get("onionServicePublicKey"):
        raise ValueError("onion mirror head public key does not match trusted policy")

    cid = head.get("rootCid")
    if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9]+", cid):
        raise ValueError("onion mirror head contains an invalid root CID")
    sequence = head.get("rootSequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("onion mirror rootSequence must be a positive integer")
    previous = head.get("previousRootCid")
    if previous is not None and (
        not isinstance(previous, str)
        or not re.fullmatch(r"[A-Za-z0-9]+", previous)
    ):
        raise ValueError("onion mirror head has an invalid previous root CID")
    digest = head.get("rootDigest")
    if not isinstance(digest, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", digest
    ):
        raise ValueError("onion mirror head has an invalid root digest")

    ok, reason = verify_signature(
        head,
        policy.get("trustedLeaders") or {},
        False,
    )
    if not ok:
        raise ValueError(f"onion mirror head signature rejected: {reason}")
    return head


def _atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        write_json(temporary, value)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish_mirror(
    policy: dict,
    publisher_state: dict,
    root: dict,
    snapshot_dir: Path,
    signing_key: Path,
) -> dict:
    leader = publisher_state.get("publisher")
    trusted = (policy.get("trustedLeaders") or {}).get(leader) or {}
    if not enabled(policy) or not trusted.get("onionMirror"):
        return {"status": "disabled"}

    cid = publisher_state["rootCid"]
    destination = mirror_path(policy) / "ipfs" / cid
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{cid}-",
                dir=destination.parent,
            )
        )
        try:
            shutil.copytree(snapshot_dir, staging, dirs_exist_ok=True)
            for directory in [staging, *staging.glob("**/*")]:
                if directory.is_dir():
                    directory.chmod(0o755)
                elif directory.is_file():
                    directory.chmod(0o644)
            os.replace(staging, destination)
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    head = build_head(policy, publisher_state, root, signing_key)
    _atomic_write(mirror_path(policy) / "heads" / f"{leader}.json", head)
    return {
        "status": "published",
        "rootCid": cid,
        "rootSequence": head["rootSequence"],
    }


def _download(
    policy: dict,
    url: str,
    destination: Path,
    maximum_bytes: int,
) -> None:
    config = _config(policy)
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "curl",
        "--fail",
        "--silent",
        "--show-error",
        "--proto",
        "=http",
        "--socks5-hostname",
        config.get("socksProxy") or "127.0.0.1:9050",
        "--connect-timeout",
        str(int(config.get("connectTimeoutSeconds", 20))),
        "--max-time",
        str(int(config.get("fetchTimeoutSeconds", 120))),
        "--max-filesize",
        str(maximum_bytes),
        "--output",
        str(destination),
        url,
    ]
    subprocess.run(command, check=True)


def fetch_head(policy: dict, leader: str) -> dict:
    mirror = (policy.get("trustedLeaders") or {}).get(leader, {}).get(
        "onionMirror"
    )
    if not enabled(policy) or not mirror:
        raise ValueError(f"leader {leader!r} has no enabled onion mirror")
    with tempfile.TemporaryDirectory(prefix="cluster-identity-onion-head-") as tmp:
        destination = Path(tmp) / "head.json"
        _download(
            policy,
            f"{_base_url(mirror)}/heads/{leader}.json",
            destination,
            int(_config(policy).get("maxHeadBytes", 1048576)),
        )
        return validate_head(policy, leader, read_json(destination, {}) or {})


def _content_paths(root: dict) -> list[str]:
    paths = []
    content = root.get("content") or {}
    if not isinstance(content, dict):
        raise ValueError("mirrored root content index is invalid")
    for entries in content.values():
        if not isinstance(entries, list):
            raise ValueError("mirrored root content index is invalid")
        for entry in entries:
            relative = entry.get("path") if isinstance(entry, dict) else None
            path = PurePosixPath(relative) if isinstance(relative, str) else None
            if (
                path is None
                or path.is_absolute()
                or ".." in path.parts
                or not path.parts
            ):
                raise ValueError("mirrored root contains an unsafe content path")
            paths.append(path.as_posix())
    return paths


def _validate_root_header(policy: dict, leader: str, root: dict) -> None:
    trusted = (policy.get("trustedLeaders") or {}).get(leader) or {}
    public_key = trusted.get("publicSigningKey")
    if not public_key:
        raise ValueError(f"onion mirror leader {leader!r} is not trusted")
    expected_key_id = key_fingerprint(public_key)
    if root.get("schema") != "cluster.identity.root.v1":
        raise ValueError("onion mirror root has an invalid schema")
    if root.get("clusterId") != cluster_id(policy):
        raise ValueError("onion mirror root is for another cluster")
    if root.get("publisher") != leader:
        raise ValueError("onion mirror root has the wrong publisher")
    if root.get("publisherKeyId") != expected_key_id:
        raise ValueError("onion mirror root has the wrong publisher key")
    ok, reason = verify_signature(
        root,
        policy.get("trustedLeaders") or {},
        False,
    )
    if not ok:
        raise ValueError(f"onion mirror root signature rejected: {reason}")


def fetch_snapshot(
    policy: dict,
    leader: str,
    cid: str,
    destination: Path,
) -> None:
    mirror = (policy.get("trustedLeaders") or {}).get(leader, {}).get(
        "onionMirror"
    )
    if not enabled(policy) or not mirror:
        raise ValueError(f"leader {leader!r} has no enabled onion mirror")
    base = f"{_base_url(mirror)}/ipfs/{cid}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}-",
            dir=destination.parent,
        )
    )
    try:
        config = _config(policy)
        _download(
            policy,
            f"{base}/root.json",
            staging / "root.json",
            int(config.get("maxRootBytes", 4194304)),
        )
        root = read_json(staging / "root.json", {}) or {}
        _validate_root_header(policy, leader, root)
        for relative in _content_paths(root):
            _download(
                policy,
                f"{base}/{relative}",
                staging / relative,
                int(config.get("maxObjectBytes", 1073741824)),
            )
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging, destination)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
