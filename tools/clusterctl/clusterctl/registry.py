import subprocess
from pathlib import Path

from . import apply as apply_mod
from . import transport
from .events import VALID_STATES, iter_json_files, read_json, write_json
from .signing import verify_signature

def ensure_registry(registry: Path) -> None:
    for name in ["events", "receipts", "bundles", "state", "policy"]:
        (registry / name).mkdir(parents=True, exist_ok=True)


def init_registry(registry: Path) -> None:
    ensure_registry(registry)
    if not (registry / ".git").exists():
        subprocess.run(["git", "-C", str(registry), "init", "-b", "main"], check=True)
    else:
        subprocess.run(["git", "-C", str(registry), "checkout", "-B", "main"], check=False)
    subprocess.run(
        [
            "git",
            "-C",
            str(registry),
            "config",
            "--local",
            "receive.denyCurrentBranch",
            "updateInstead",
        ],
        check=False,
    )
    transport.ensure_git_identity(registry)


def load_events(registry: Path) -> list[tuple[Path, dict]]:
    events = []
    for path in iter_json_files(registry / "events"):
        events.append((path, read_json(path, {})))
    return events


def load_receipts(registry: Path) -> list[tuple[Path, dict]]:
    receipts = []
    for path in iter_json_files(registry / "receipts"):
        receipts.append((path, read_json(path, {})))
    return receipts


def load_bundle_manifests(registry: Path) -> list[tuple[Path, dict]]:
    manifests = []
    for path in sorted((registry / "bundles").glob("**/*.manifest.json")):
        if path.is_file():
            manifests.append((path, read_json(path, {})))
    return manifests


def receipt_exists(receipts: list[tuple[Path, dict]], node: str, service: str, generation: int) -> bool:
    for _path, receipt in receipts:
        if (
            receipt.get("node") == node
            and receipt.get("service") == service
            and receipt.get("generation") == generation
            and (receipt.get("activated") is True or receipt.get("status") in {"node-activated", "leader-verified"})
        ):
            return True
    return False


def _valid_public_fields(service: str, public: dict) -> list[str]:
    if not isinstance(public, dict):
        return ["public must be an object"]
    failures: list[str] = []
    if service == "yggdrasil":
        if not public.get("yggdrasilPublicKey"):
            failures.append("yggdrasil public data missing yggdrasilPublicKey")
        if not (public.get("yggdrasilAddress") or public.get("deployHost")):
            failures.append("yggdrasil public data missing yggdrasilAddress or deployHost")
    elif service == "ssh-host":
        if not (public.get("sshHostKey") or public.get("publicKey")):
            failures.append("ssh-host public data missing sshHostKey")
    elif service == "host-age":
        if not public.get("ageRecipient"):
            failures.append("host-age public data missing ageRecipient")
        if public.get("keyType") not in {None, "age-x25519"}:
            failures.append(f"host-age public data has unsupported keyType {public.get('keyType')!r}")
        if not public.get("privateKeyPath"):
            failures.append("host-age public data missing privateKeyPath")
    elif service == "radicle":
        if not public.get("radicleNodeId"):
            failures.append("radicle public data missing radicleNodeId")
    elif service == "git-annex":
        if not public.get("gitAnnexEndpoint"):
            failures.append("git-annex public data missing gitAnnexEndpoint")
    else:
        allowed_unknown = {"sourceTimestamp", "keyGeneratedAt", "fingerprint"}
        if not any(key not in allowed_unknown for key in public):
            failures.append(f"{service} public data has no service-specific fields")
    return failures


def _valid_private_delivery(private_delivery: dict) -> list[str]:
    if not isinstance(private_delivery, dict):
        return ["privateDelivery must be an object or null"]
    failures: list[str] = []
    if private_delivery.get("recipientHost") is not None and not isinstance(private_delivery.get("recipientHost"), str):
        failures.append("privateDelivery.recipientHost must be a string")
    if private_delivery.get("targetPath") is not None and not str(private_delivery.get("targetPath")).startswith("/"):
        failures.append("privateDelivery.targetPath must be absolute")
    if private_delivery.get("requiresReceipt") is not None and not isinstance(private_delivery.get("requiresReceipt"), bool):
        failures.append("privateDelivery.requiresReceipt must be a boolean")
    for field in ["sopsPath", "bundleManifest", "bundlePath", "recipientFingerprint"]:
        if private_delivery.get(field) is not None and not isinstance(private_delivery.get(field), str):
            failures.append(f"privateDelivery.{field} must be a string")
    return failures


def validate_registry(registry: Path, policy: dict | None = None) -> list[str]:
    policy = policy or {}
    trusted = policy.get("trustedLeaders", {})
    rules = policy.get("policy", policy)
    allow_placeholder = bool(rules.get("allowPlaceholderSignatures", False))
    failures: list[str] = []
    receipts = load_receipts(registry)
    burned = set()

    for path, event in load_events(registry):
        subject = event.get("subject") or {}
        for field in ["schema", "eventId", "generation", "state", "leader", "leaderKey"]:
            if field not in event:
                failures.append(f"{path}: missing {field}")
        if event.get("schema") != "cluster.identity.event.v1":
            failures.append(f"{path}: invalid schema {event.get('schema')!r}")
        if not subject.get("node"):
            failures.append(f"{path}: missing subject.node")
        if not subject.get("service"):
            failures.append(f"{path}: missing subject.service")
        if not isinstance(event.get("generation"), int):
            failures.append(f"{path}: generation must be an integer")
        if event.get("state") not in VALID_STATES:
            failures.append(f"{path}: invalid state {event.get('state')!r}")
        if event.get("public") is not None:
            for failure in _valid_public_fields(subject.get("service"), event.get("public") or {}):
                failures.append(f"{path}: {failure}")
        private_delivery = event.get("privateDelivery")
        if private_delivery is not None:
            for failure in _valid_private_delivery(private_delivery):
                failures.append(f"{path}: {failure}")
        ok, reason = verify_signature(event, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {reason}")
        if event.get("state") == "burned":
            fingerprint = (event.get("burned") or {}).get("fingerprint")
            if not fingerprint:
                failures.append(f"{path}: burned event missing burned.fingerprint")
            else:
                burned.add(fingerprint)
        private_delivery = event.get("privateDelivery") or {}
        requires_receipt = bool(private_delivery.get("requiresReceipt"))
        if (
            rules.get("requireReceiptBeforePromote", False)
            and requires_receipt
            and event.get("state") == "active"
            and isinstance(event.get("generation"), int)
            and not receipt_exists(receipts, subject.get("node"), subject.get("service"), event["generation"])
        ):
            failures.append(f"{path}: active private-delivery event is missing activation receipt")

    for path, receipt in receipts:
        for field in ["schema", "node", "service", "generation", "status", "createdAt", "signature"]:
            if field not in receipt:
                failures.append(f"{path}: missing {field}")
        if receipt.get("schema") != "cluster.identity.receipt.v1":
            failures.append(f"{path}: invalid schema {receipt.get('schema')!r}")
        if not isinstance(receipt.get("generation"), int):
            failures.append(f"{path}: generation must be an integer")
        ok, reason = verify_signature(receipt, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {reason}")

    for path, manifest in load_bundle_manifests(registry):
        for field in ["schema", "subject", "generation", "targetPath", "encryption", "bundle", "leader", "leaderKey", "signature"]:
            if field not in manifest:
                failures.append(f"{path}: missing {field}")
        if manifest.get("schema") != "cluster.identity.bundle.v1":
            failures.append(f"{path}: invalid schema {manifest.get('schema')!r}")
        subject = manifest.get("subject") or {}
        if not subject.get("node"):
            failures.append(f"{path}: missing subject.node")
        if not subject.get("service"):
            failures.append(f"{path}: missing subject.service")
        if not isinstance(manifest.get("generation"), int):
            failures.append(f"{path}: generation must be an integer")
        encryption = manifest.get("encryption") or {}
        if encryption.get("method") != "age-x25519":
            failures.append(f"{path}: unsupported encryption method {encryption.get('method')!r}")
        if not encryption.get("recipientPublicKey"):
            failures.append(f"{path}: missing encryption.recipientPublicKey")
        bundle = manifest.get("bundle") or {}
        if not bundle.get("path"):
            failures.append(f"{path}: missing bundle.path")
        ok, reason = verify_signature(manifest, trusted, allow_placeholder)
        if not ok:
            failures.append(f"{path}: {reason}")

    for path, event in load_events(registry):
        if event.get("state") == "burned":
            continue
        public = event.get("public") or {}
        fingerprints = [value for key, value in public.items() if "fingerprint" in key.lower()]
        for fingerprint in fingerprints:
            if fingerprint in burned:
                failures.append(f"{path}: reintroduces burned fingerprint {fingerprint}")

    return failures


def _empty_generated(generated_from: list[str]) -> dict:
    return {
        "schema": "cluster.identity.state.v1",
        "generatedFrom": generated_from,
        "nodes": {},
    }


def _put(state: dict, node: str, service: str, event: dict) -> None:
    state["nodes"].setdefault(node, {})[service] = {
        "generation": event["generation"],
        "state": event["state"],
        "leader": event.get("leader"),
        "eventId": event.get("eventId"),
        "public": event.get("public", {}),
        "privateDelivery": event.get("privateDelivery"),
        "localUsable": event.get("localUsable", True),
        "createdAt": event.get("createdAt"),
    }


def _event_order(event: dict) -> tuple[str, int]:
    public = event.get("public") or {}
    key_generated_at = (
        public.get("keyGeneratedAt")
        or public.get("sourceTimestamp")
        or event.get("keyGeneratedAt")
        or event.get("sourceTimestamp")
        or ""
    )
    generation = event.get("generation")
    return (key_generated_at, generation if isinstance(generation, int) else -1)


def reconcile(registry: Path, out: Path | None = None, policy: dict | None = None) -> None:
    ensure_registry(registry)
    policy = policy or {}
    rules = policy.get("policy", policy)
    receipts = load_receipts(registry)
    event_pairs = load_events(registry)
    local_host = policy.get("hostName")
    host_age_key = policy.get("sopsAgeKeyFile") or policy.get("hostAgeKeyFile")
    generated = [event.get("eventId") for _path, event in event_pairs if event.get("eventId")]
    active = _empty_generated(generated)
    staged = _empty_generated(generated)
    deprecated = _empty_generated(generated)
    burned = _empty_generated(generated)
    selected: dict[tuple[str, str, str], dict] = {}
    burned_subjects: set[tuple[str, str]] = set()

    for _path, event in event_pairs:
        subject = event.get("subject") or {}
        node = subject.get("node")
        service = subject.get("service")
        generation = event.get("generation")
        state = event.get("state")
        if not node or not service or not isinstance(generation, int) or state not in VALID_STATES:
            continue
        if state == "burned":
            burned_subjects.add((node, service))
            _put(burned, node, service, event)
            continue
        if state == "removed":
            continue
        if state == "active":
            private_delivery = event.get("privateDelivery") or {}
            requires_receipt = bool(private_delivery.get("requiresReceipt"))
            if rules.get("requireReceiptBeforePromote", False) and requires_receipt:
                if not receipt_exists(receipts, node, service, generation):
                    state = "staged"
            if local_host and node == local_host and private_delivery.get("bundleManifest"):
                manifest = registry / private_delivery["bundleManifest"]
                if not _manifest_decryptable(registry, manifest, host_age_key):
                    event = event | {"localUsable": False}
                    state = "staged"
        key = (state, node, service)
        if _event_order(event) > _event_order(selected.get(key, {})):
            selected[key] = event | {"state": state}

    for (state, node, service), event in selected.items():
        if (node, service) in burned_subjects and state != "deprecated":
            continue
        if state == "active":
            _put(active, node, service, event)
        elif state in {"planned", "staged", "private-delivered", "node-received", "node-activated", "leader-verified"}:
            _put(staged, node, service, event)
        elif state == "deprecated":
            _put(deprecated, node, service, event)

    if out is None:
        _write_registry_state(registry, active, staged, deprecated, burned)
    else:
        _write_materialized_state(out, active, staged, deprecated, burned)


def _manifest_decryptable(registry: Path, manifest: Path, host_age_key: str | None) -> bool:
    if not host_age_key:
        return False
    manifest_data = read_json(manifest, {}) or {}
    bundle = manifest_data.get("bundle") or {}
    bundle_path = bundle.get("path")
    if not bundle_path:
        return False
    encrypted = registry / bundle_path
    if not encrypted.exists():
        encrypted = manifest.parent / Path(bundle_path).name
    if not encrypted.exists():
        return False
    completed = subprocess.run(
        ["age", "-d", "-i", host_age_key, str(encrypted)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return completed.returncode == 0


def _service_views(active: dict) -> tuple[list[str], dict[str, dict], dict[str, dict], dict[str, dict]]:
    known_hosts: list[str] = []
    yggdrasil: dict[str, dict] = {}
    radicle: dict[str, dict] = {}
    annex: dict[str, dict] = {}
    for node, services in active.get("nodes", {}).items():
        ssh = services.get("ssh-host", {}).get("public", {})
        ssh_key = ssh.get("sshHostKey") or ssh.get("publicKey")
        if ssh_key:
            known_hosts.append(f"{node} {ssh_key}")
        ygg = services.get("yggdrasil", {}).get("public", {})
        if ygg:
            yggdrasil[node] = ygg
        rad = services.get("radicle", {}).get("public", {})
        if rad:
            radicle[node] = rad
        git_annex = services.get("git-annex", {}).get("public", {})
        if git_annex:
            annex[node] = git_annex
    return known_hosts, yggdrasil, radicle, annex


def _write_registry_state(registry: Path, active: dict, staged: dict, deprecated: dict, burned: dict) -> None:
    state = registry / "state"
    state.mkdir(parents=True, exist_ok=True)
    write_json(state / "active.json", active)
    write_json(state / "staged.json", staged)
    write_json(state / "deprecated.json", deprecated)
    write_json(state / "burned.json", burned)
    known_hosts, yggdrasil, radicle, annex = _service_views(active)
    (state / "known_hosts").write_text("\n".join(known_hosts) + ("\n" if known_hosts else ""), encoding="utf-8")
    write_json(state / "yggdrasil-peers.json", yggdrasil)
    write_json(state / "radicle-nodes.json", radicle)
    write_json(state / "git-annex-remotes.json", annex)


def _write_materialized_state(out: Path, active: dict, staged: dict, deprecated: dict, burned: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "active.json", active)
    write_json(out / "staged.json", staged)
    write_json(out / "deprecated.json", deprecated)
    write_json(out / "burned.json", burned)
    known_hosts, yggdrasil, radicle, annex = _service_views(active)
    (out / "ssh_known_hosts").write_text("\n".join(known_hosts) + ("\n" if known_hosts else ""), encoding="utf-8")
    for subdir in ["yggdrasil", "radicle", "git-annex"]:
        (out / subdir).mkdir(parents=True, exist_ok=True)
    write_json(out / "yggdrasil" / "peers.json", yggdrasil)
    write_json(out / "radicle" / "nodes.json", radicle)
    write_json(out / "git-annex" / "remotes.json", annex)


def sync(registry: Path, out: Path, policy: dict | None = None) -> None:
    transport.git_fetch_all(registry, policy)
    reconcile(registry, out, policy)
    apply_mod.apply_materialized(registry, out, policy)
