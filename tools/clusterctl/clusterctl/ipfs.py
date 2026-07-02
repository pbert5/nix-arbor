import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .canonical import canonical_bytes


def _command(policy: dict, *args: str) -> list[str]:
    registry = policy.get("registry") or {}
    ipfs = registry.get("ipfs") or {}
    command = ["ipfs"]
    api = ipfs.get("api")
    if api:
        command.append(f"--api={api}")
    command.extend(args)
    return command


def _capture(policy: dict, *args: str, timeout: int | None = None) -> str:
    completed = subprocess.run(
        _command(policy, *args),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return completed.stdout.strip()


def key_names(policy: dict, *, attempts: int = 1, retry_delay: float = 1.0) -> dict[str, str]:
    output = None
    last_error = None
    for attempt in range(attempts):
        try:
            output = _capture(policy, "key", "ls", "-l")
            break
        except subprocess.CalledProcessError as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(retry_delay)
    if output is None:
        raise last_error or RuntimeError("Kubo API did not become ready")
    keys: dict[str, str] = {}
    for line in output.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) == 2:
            keys[parts[1].strip()] = parts[0]
    return keys


def ensure_ipns_key(
    policy: dict,
    key_name: str,
    key_file: Path,
    expected_ipns_name: str,
) -> str:
    current = key_names(policy, attempts=180, retry_delay=1.0)
    if key_name not in current:
        imported = _capture(
            policy,
            "key",
            "import",
            "--format=pem-pkcs8-cleartext",
            key_name,
            str(key_file),
        )
        current = key_names(policy)
        if key_name not in current:
            raise RuntimeError(f"Kubo did not retain imported IPNS key {key_name!r}: {imported}")
    actual = current[key_name]
    if actual != expected_ipns_name:
        raise ValueError(
            f"IPNS key {key_name!r} resolves to {actual}, expected trusted name {expected_ipns_name}"
        )
    return actual


def generate_key(policy: dict, key_name: str) -> str:
    if key_name in key_names(policy):
        raise ValueError(f"IPNS key {key_name!r} already exists")
    return _capture(policy, "key", "gen", "--type=ed25519", key_name)


def add_directory(policy: dict, directory: Path) -> str:
    cid = _capture(
        policy,
        "add",
        "--quieter",
        "--recursive",
        "--cid-version=1",
        "--pin=true",
        str(directory),
    ).splitlines()[-1]
    if not cid.startswith("b"):
        raise RuntimeError(f"Kubo returned an invalid CID: {cid!r}")
    return cid


def publish_name(
    policy: dict,
    key_name: str,
    expected_ipns_name: str,
    root_cid: str,
) -> str:
    keys = key_names(policy)
    actual = keys.get(key_name)
    if actual != expected_ipns_name:
        raise ValueError(
            f"refusing IPNS publish: key {key_name!r} is {actual!r}, expected {expected_ipns_name!r}"
        )
    registry = policy.get("registry") or {}
    config = registry.get("ipfs") or {}
    output = _capture(
        policy,
        "name",
        "publish",
        f"--key={key_name}",
        f"--lifetime={config.get('ipnsLifetime', '168h')}",
        f"--ttl={config.get('ipnsTtl', '5m')}",
        "--allow-offline",
        f"/ipfs/{root_cid}",
    )
    return output


def pin(policy: dict, cid: str) -> None:
    _capture(policy, "pin", "add", "--recursive=true", cid)


def resolve_name(policy: dict, ipns_name: str) -> str:
    config = ((policy.get("registry") or {}).get("ipfs") or {})
    timeout = int(config.get("resolveTimeoutSeconds", 60))
    resolved = _capture(
        policy,
        "name",
        "resolve",
        "--nocache",
        "--recursive=true",
        f"/ipns/{ipns_name}",
        timeout=timeout,
    )
    prefix = "/ipfs/"
    if not resolved.startswith(prefix):
        raise ValueError(f"IPNS name {ipns_name!r} resolved to invalid path {resolved!r}")
    cid = resolved[len(prefix) :].split("/", 1)[0]
    if not re.fullmatch(r"[A-Za-z0-9]+", cid):
        raise ValueError(f"IPNS name {ipns_name!r} resolved to invalid CID {cid!r}")
    return cid


def fetch_directory(
    policy: dict,
    cid: str,
    destination: Path,
    required_file: str = "root.json",
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9]+", cid):
        raise ValueError(f"invalid CID {cid!r}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    payload = work / "snapshot"
    try:
        _capture(policy, "get", f"--output={payload}", f"/ipfs/{cid}")
        if required_file and not (payload / required_file).is_file():
            raise RuntimeError(f"CID {cid} did not contain {required_file}")
        if destination.exists():
            shutil.rmtree(destination)
        payload.replace(destination)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def publish_pubsub(policy: dict, topic: str, message: dict) -> None:
    config = ((policy.get("registry") or {}).get("pubsub") or {})
    timeout = int(config.get("publishTimeoutSeconds", 15))
    with tempfile.TemporaryDirectory(prefix="cluster-identity-pubsub-") as tmp:
        payload = Path(tmp) / "announcement.json"
        payload.write_bytes(canonical_bytes(message))
        _capture(
            policy,
            "pubsub",
            "pub",
            topic,
            str(payload),
            timeout=timeout,
        )


def subscribe_pubsub(policy: dict, topic: str) -> subprocess.Popen:
    return subprocess.Popen(
        _command(policy, "pubsub", "sub", "--enc=json", topic),
        text=True,
        stdout=subprocess.PIPE,
        stderr=None,
        bufsize=1,
    )
