import hashlib
import subprocess
from pathlib import Path

from .events import now_utc, write_json
from .signing import key_fingerprint, public_key_from_private, sign_record


def publish_bundle(node: str, service: str, generation: int, source: Path, target_path: str, target_host: str, ssh_user: str) -> None:
    remote_tmp = f"/tmp/cluster-identity-{service}-gen-{generation}"
    subprocess.run(["scp", str(source), f"{ssh_user}@{target_host}:{remote_tmp}"], check=True)
    subprocess.run(
        [
            "ssh",
            f"{ssh_user}@{target_host}",
            (
                f"install -D -m 0400 -o root -g root {remote_tmp} {target_path} "
                f"&& rm -f {remote_tmp} "
                "&& systemctl start cluster-identity-fetch-now.service"
            ),
        ],
        check=False,
    )


def write_receipt(
    path: Path,
    node: str,
    service: str,
    generation: int,
    status: str,
    activated: bool,
    signer: str | None,
    signing_key: Path,
    signature: str | None,
    cluster_id: str,
    event_id: str,
    bundle_manifest: str,
) -> None:
    public_key = signer or public_key_from_private(signing_key)
    receipt = {
        "schema": "cluster.identity.receipt.v1",
        "clusterId": cluster_id,
        "node": node,
        "service": service,
        "generation": generation,
        "status": status,
        "activated": activated,
        "eventId": event_id,
        "bundleManifest": bundle_manifest,
        "observedPublic": {},
        "signedByNode": {
            "node": node,
            "keyType": "ssh-host",
            "keyId": key_fingerprint(public_key),
            "publicKey": public_key,
        },
        "createdAt": now_utc(),
    }
    if signature:
        receipt["signature"] = {
            "type": "openssh",
            "namespace": "cluster-identity",
            "keyId": key_fingerprint(public_key),
            "value": signature,
        }
    else:
        receipt["signature"] = sign_record(receipt, signing_key)
    write_json(path, receipt)


def collect_receipt(node: str, service: str, generation: int, target_host: str, ssh_user: str, destination: Path) -> None:
    remote = f"/var/lib/cluster-identity/receipts/{node}-{service}-gen-{generation}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["scp", f"{ssh_user}@{target_host}:{remote}", str(destination)], check=True)


def seal_bundle(
    *,
    registry: Path,
    node: str,
    service: str,
    generation: int,
    source: Path,
    target_path: str,
    recipient_public_key: str,
    expected_public: dict,
    leader: str,
    leader_key: str,
    signing_key: Path,
    cluster_id: str,
) -> Path:
    bundle_dir = registry / "bundles" / node / service
    bundle_dir.mkdir(parents=True, exist_ok=True)
    encrypted = bundle_dir / f"gen-{generation}.age"
    manifest = bundle_dir / f"gen-{generation}.manifest.json"
    plaintext = source.read_bytes()
    subprocess.run(
        ["age", "-r", recipient_public_key, "-o", str(encrypted), str(source)],
        check=True,
    )
    ciphertext = encrypted.read_bytes()
    payload = {
        "schema": "cluster.identity.bundle.v1",
        "clusterId": cluster_id,
        "subject": {
            "node": node,
            "service": service,
        },
        "generation": generation,
        "targetPath": target_path,
        "encryption": {
            "method": "age-x25519",
            "recipientHost": node,
            "recipientPublicKey": recipient_public_key,
            "recipientFingerprint": _sha256_text(recipient_public_key),
        },
        "bundle": {
            "path": str(encrypted.relative_to(registry)),
            "ciphertextSha256": _sha256_bytes(ciphertext),
            "plaintextSha256": _sha256_bytes(plaintext),
        },
        "expectedPublic": expected_public,
        "createdAt": now_utc(),
        "leader": leader,
        "leaderKeyId": key_fingerprint(leader_key),
    }
    payload["signature"] = sign_record(payload, signing_key)
    write_json(manifest, payload)
    return manifest


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_text(data: str) -> str:
    return _sha256_bytes(data.encode("utf-8"))
