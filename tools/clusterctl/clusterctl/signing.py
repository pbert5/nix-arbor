import subprocess
import tempfile
from pathlib import Path

from .canonical import signing_payload

SIGNATURE_NAMESPACE = "cluster-identity"


def signature_present(record: dict) -> bool:
    value = record.get("signature")
    if isinstance(value, str):
        return value.strip() != ""
    return isinstance(value, dict) and isinstance(value.get("value"), str) and value["value"].strip() != ""


def placeholder_signature(leader: str, event_id: str) -> dict:
    return {
        "type": "placeholder",
        "namespace": SIGNATURE_NAMESPACE,
        "keyId": "placeholder",
        "value": f"placeholder-signature:{leader}:{event_id}",
    }


def is_placeholder_signature(signature: str) -> bool:
    return signature.startswith("placeholder-signature:")


def signature_value(signature) -> str:
    if isinstance(signature, str):
        return signature.strip()
    if isinstance(signature, dict) and isinstance(signature.get("value"), str):
        return signature["value"].strip()
    return ""


def public_key_from_private(key_path: Path) -> str:
    completed = subprocess.run(
        ["ssh-keygen", "-y", "-f", str(key_path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return completed.stdout.strip()


def key_fingerprint(public_key: str) -> str:
    with tempfile.TemporaryDirectory(prefix="cluster-identity-keyid-") as tmp:
        key_path = Path(tmp) / "key.pub"
        key_path.write_text(public_key.strip() + "\n", encoding="utf-8")
        completed = subprocess.run(
            ["ssh-keygen", "-lf", str(key_path), "-E", "sha256"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    return completed.stdout.split()[1]


def sign_record(record: dict, key_path: Path, namespace: str = SIGNATURE_NAMESPACE) -> dict:
    with tempfile.TemporaryDirectory(prefix="cluster-identity-sign-") as tmp:
        payload_path = Path(tmp) / "payload.json"
        payload_path.write_bytes(signing_payload(record))
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(key_path), "-n", namespace, str(payload_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        value = payload_path.with_suffix(".json.sig").read_text(encoding="utf-8")
    public_key = public_key_from_private(key_path)
    return {
        "type": "openssh",
        "namespace": namespace,
        "keyId": key_fingerprint(public_key),
        "value": value,
    }


def _verify_ssh_signature(record: dict, public_key: str, signature: str, principal: str) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="cluster-identity-verify-") as tmp:
        tmp_path = Path(tmp)
        payload_path = tmp_path / "payload.json"
        signature_path = tmp_path / "payload.sig"
        allowed_signers = tmp_path / "allowed_signers"
        payload_path.write_bytes(signing_payload(record))
        signature_path.write_text(signature, encoding="utf-8")
        allowed_signers.write_text(f"{principal} {public_key}\n", encoding="utf-8")
        completed = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "verify",
                "-f",
                str(allowed_signers),
                "-I",
                principal,
                "-n",
                SIGNATURE_NAMESPACE,
                "-s",
                str(signature_path),
            ],
            input=payload_path.read_bytes(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    if completed.returncode == 0:
        return True, "signature verified"
    reason = completed.stderr.decode("utf-8", errors="replace").strip() or "signature verification failed"
    return False, reason


def verify_detached_signature(
    record: dict,
    public_key: str,
    signature: dict,
    principal: str,
) -> tuple[bool, str]:
    if signature.get("type") != "openssh":
        return False, f"unsupported signature type {signature.get('type')!r}"
    if signature.get("namespace") != SIGNATURE_NAMESPACE:
        return False, f"invalid signature namespace {signature.get('namespace')!r}"
    expected_key_id = key_fingerprint(public_key)
    if signature.get("keyId") != expected_key_id:
        return False, "signature keyId does not match trusted key"
    return _verify_ssh_signature(record, public_key, signature_value(signature), principal)


def verify_signature(record: dict, trusted_leaders: dict, allow_placeholder: bool = False) -> tuple[bool, str]:
    if not signature_present(record):
        return False, "missing signature"
    signature_object = record["signature"]
    signature = signature_value(signature_object)
    if is_placeholder_signature(signature):
        if allow_placeholder:
            return True, "placeholder signature accepted by policy"
        return False, "placeholder signature rejected by policy"

    if not isinstance(signature_object, dict):
        return False, "legacy string signatures are not canonical registry v1 signatures"
    if signature_object.get("type") != "openssh":
        return False, f"unsupported signature type {signature_object.get('type')!r}"
    if signature_object.get("namespace") != SIGNATURE_NAMESPACE:
        return False, f"invalid signature namespace {signature_object.get('namespace')!r}"

    leader = record.get("leader") or record.get("publisher")
    if leader:
        trusted = trusted_leaders.get(leader) or {}
        public_key = trusted.get("publicSigningKey")
        if not public_key:
            return False, f"untrusted leader {leader!r}"
        if trusted.get("canWrite") is False:
            return False, f"leader {leader!r} is not allowed to write"
        expected_key_id = trusted.get("keyId") or key_fingerprint(public_key)
        record_key_id = record.get("leaderKeyId") or record.get("publisherKeyId")
        if record_key_id != expected_key_id:
            return False, f"leaderKeyId for {leader!r} does not match trusted policy"
        if signature_object.get("keyId") != expected_key_id:
            return False, f"signature keyId for {leader!r} does not match trusted policy"
        return _verify_ssh_signature(record, public_key, signature, leader)

    signed_by_node = record.get("signedByNode")
    node = record.get("node")
    if signed_by_node and node:
        if isinstance(signed_by_node, dict):
            public_key = signed_by_node.get("publicKey")
            expected_key_id = signed_by_node.get("keyId")
        else:
            public_key = signed_by_node
            expected_key_id = key_fingerprint(public_key)
        if not public_key:
            return False, "node receipt has no public verification key"
        if expected_key_id != key_fingerprint(public_key):
            return False, "node receipt keyId does not match its public key"
        if signature_object.get("keyId") != expected_key_id:
            return False, "node receipt signature keyId does not match signedByNode"
        return _verify_ssh_signature(record, public_key, signature, node)

    return False, "real signature has no trusted verification key"
