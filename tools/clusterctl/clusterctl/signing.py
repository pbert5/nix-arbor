import json
import subprocess
import tempfile
from pathlib import Path

SIGNATURE_NAMESPACE = "cluster-identity"


def signature_present(record: dict) -> bool:
    value = record.get("signature")
    return isinstance(value, str) and value.strip() != ""


def placeholder_signature(leader: str, event_id: str) -> str:
    return f"placeholder-signature:{leader}:{event_id}"


def is_placeholder_signature(signature: str) -> bool:
    return signature.startswith("placeholder-signature:")


def signing_payload(record: dict) -> bytes:
    unsigned = {key: value for key, value in record.items() if key != "signature"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_record(record: dict, key_path: Path, namespace: str = SIGNATURE_NAMESPACE) -> str:
    with tempfile.TemporaryDirectory(prefix="cluster-identity-sign-") as tmp:
        payload_path = Path(tmp) / "payload.json"
        payload_path.write_bytes(signing_payload(record))
        subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", str(key_path), "-n", namespace, str(payload_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return payload_path.with_suffix(".json.sig").read_text(encoding="utf-8")


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


def verify_signature(record: dict, trusted_leaders: dict, allow_placeholder: bool = True) -> tuple[bool, str]:
    if not signature_present(record):
        return False, "missing signature"
    signature = record["signature"].strip()
    if is_placeholder_signature(signature):
        if allow_placeholder:
            return True, "placeholder signature accepted by policy"
        return False, "placeholder signature rejected by policy"

    leader = record.get("leader")
    if leader:
        trusted = trusted_leaders.get(leader) or {}
        public_key = trusted.get("publicSigningKey")
        if not public_key:
            return False, f"untrusted leader {leader!r}"
        if trusted.get("canWrite") is False:
            return False, f"leader {leader!r} is not allowed to write"
        if record.get("leaderKey") and record["leaderKey"] != public_key:
            return False, f"leaderKey for {leader!r} does not match trusted policy"
        return _verify_ssh_signature(record, public_key, signature, leader)

    signed_by_node = record.get("signedByNode")
    node = record.get("node")
    if signed_by_node and node:
        return _verify_ssh_signature(record, signed_by_node, signature, node)

    return False, "real signature has no trusted verification key"
