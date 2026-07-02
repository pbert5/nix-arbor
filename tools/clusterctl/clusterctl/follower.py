import os
import re
import shutil
import tempfile
from pathlib import Path

from . import apply as apply_mod
from . import ipfs, onion
from . import registry as registry_mod
from .canonical import canonical_sha256, sha256_bytes
from .events import now_utc, read_json, write_json


SOURCE_DIRECTORIES = ["events", "bundles", "receipts"]


def _registry_config(policy: dict) -> dict:
    return policy.get("registry") or {}


def cache_path(policy: dict) -> Path:
    configured = _registry_config(policy).get("followerCachePath")
    return Path(configured or "/var/lib/cluster-identity/follower-cache")


def accepted_registry_path(policy: dict) -> Path:
    configured = _registry_config(policy).get("acceptedRegistryPath")
    return Path(configured or "/var/lib/cluster-identity/accepted-registry")


def _snapshot_path(policy: dict, leader: str, cid: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9]+", cid):
        raise ValueError(f"invalid checkpoint CID {cid!r}")
    return cache_path(policy) / leader / cid


def _validate_snapshot(path: Path, policy: dict, leader: str) -> dict:
    failures = registry_mod.validate_registry(path, policy)
    if failures:
        raise ValueError("snapshot verification failed:\n" + "\n".join(f"- {item}" for item in failures))
    root = read_json(path / "root.json", {}) or {}
    if root.get("publisher") != leader:
        raise ValueError(
            f"IPNS head for {leader!r} contains a root published by {root.get('publisher')!r}"
        )
    return root


def _load_snapshot(
    policy: dict,
    leader: str,
    cid: str,
) -> tuple[Path, dict, str]:
    path = _snapshot_path(policy, leader, cid)
    transport = "cache"
    if not (path / "root.json").is_file():
        try:
            ipfs.fetch_directory(policy, cid, path)
            transport = "ipfs"
        except Exception as ipfs_error:
            try:
                onion.fetch_snapshot(policy, leader, cid, path)
                transport = "onion"
            except Exception as onion_error:
                raise RuntimeError(
                    f"IPFS fetch failed: {ipfs_error}; "
                    f"onion mirror fetch failed: {onion_error}"
                ) from onion_error
    return path, _validate_snapshot(path, policy, leader), transport


def _descends_from(
    policy: dict,
    leader: str,
    candidate_cid: str,
    candidate_root: dict,
    accepted_head: dict,
) -> bool:
    accepted_cid = accepted_head.get("cid")
    accepted_sequence = accepted_head.get("rootSequence")
    if not isinstance(accepted_cid, str) or not isinstance(accepted_sequence, int):
        return False

    cursor_cid = candidate_cid
    cursor_root = candidate_root
    seen = {cursor_cid}
    while cursor_root.get("rootSequence", 0) > accepted_sequence:
        sequence = cursor_root.get("rootSequence")
        previous = cursor_root.get("previousRootCid")
        if not isinstance(sequence, int) or not isinstance(previous, str):
            return False
        if sequence == accepted_sequence + 1:
            return previous == accepted_cid
        if previous in seen:
            return False
        seen.add(previous)
        _path, prior_root, _transport = _load_snapshot(
            policy,
            leader,
            previous,
        )
        if prior_root.get("rootSequence") != sequence - 1:
            return False
        cursor_cid = previous
        cursor_root = prior_root
    return cursor_cid == accepted_cid


def _candidate_allowed(
    policy: dict,
    leader: str,
    cid: str,
    root: dict,
    accepted_head: dict | None,
    snapshot: Path,
) -> tuple[bool, str]:
    if accepted_head is None:
        return True, "first-valid-head"
    previous_sequence = accepted_head.get("rootSequence")
    sequence = root.get("rootSequence")
    previous_cid = accepted_head.get("cid")
    if not isinstance(previous_sequence, int) or not isinstance(sequence, int):
        return False, "invalid-checkpoint-sequence"
    if sequence < previous_sequence:
        return False, "root-sequence-rollback"
    if sequence == previous_sequence:
        if cid == previous_cid:
            return True, "unchanged"
        return False, "same-sequence-equivocation"
    accepted_tip = accepted_head.get("eventChainTip")
    if not isinstance(accepted_tip, dict) and isinstance(previous_cid, str):
        previous_path, _previous_root, _previous_transport = _load_snapshot(
            policy, leader, previous_cid
        )
        accepted_tip = registry_mod.leader_chain_tip(previous_path, leader)
    if isinstance(accepted_tip, dict):
        candidate_tip = root.get("eventChainTip")
        accepted_event_sequence = accepted_tip.get("leaderSeq")
        if (
            not isinstance(candidate_tip, dict)
            or not isinstance(accepted_event_sequence, int)
            or candidate_tip.get("leaderSeq", -1) < accepted_event_sequence
        ):
            return False, "leader-event-chain-rollback"
        retained = next(
            (
                record
                for _path, record in registry_mod.load_events(snapshot)
                if record.get("leader") == leader
                and record.get("leaderSeq") == accepted_event_sequence
            ),
            None,
        )
        if retained is None or retained.get("eventHash") != accepted_tip.get(
            "eventHash"
        ):
            return False, "leader-event-chain-does-not-descend-from-last-good"
    if not _descends_from(policy, leader, cid, root, accepted_head):
        return False, "root-history-does-not-descend-from-last-good"
    return True, "newer-descendant"


def _copy_file(source: Path, destination: Path, conflicts: set[str], root: Path) -> None:
    relative = destination.relative_to(root).as_posix()
    if relative in conflicts:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copyfile(source, destination)
        return
    if source.read_bytes() != destination.read_bytes():
        destination.unlink()
        conflicts.add(relative)


def _copy_leader_content(leader: str, snapshot: Path, aggregate: Path, conflicts: set[str]) -> None:
    events = snapshot / "events" / leader
    if events.exists():
        for source in sorted(events.glob("**/*.json")):
            _copy_file(source, aggregate / source.relative_to(snapshot), conflicts, aggregate)

    for manifest_path in sorted((snapshot / "bundles").glob("**/*.manifest.json")):
        manifest = read_json(manifest_path, {}) or {}
        if manifest.get("leader") != leader:
            continue
        _copy_file(manifest_path, aggregate / manifest_path.relative_to(snapshot), conflicts, aggregate)
        bundle_path = (manifest.get("bundle") or {}).get("path")
        if not isinstance(bundle_path, str) or not bundle_path.startswith("bundles/"):
            continue
        source = snapshot / bundle_path
        if source.is_file():
            _copy_file(source, aggregate / bundle_path, conflicts, aggregate)

    for receipt in sorted((snapshot / "receipts").glob("**/*.json")):
        digest = sha256_bytes(receipt.read_bytes()).split(":", 1)[1]
        destination = aggregate / "receipts" / "merged" / f"{digest}.json"
        _copy_file(receipt, destination, conflicts, aggregate)


def _build_aggregate(snapshots: dict[str, Path], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    for directory in [*SOURCE_DIRECTORIES, "state", "policy"]:
        (staging / directory).mkdir(parents=True, exist_ok=True)
    conflicts: set[str] = set()
    for leader, snapshot in sorted(snapshots.items()):
        _copy_leader_content(leader, snapshot, staging, conflicts)
    return staging


def _replace_directory(staging: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}.old")
    if backup.exists():
        shutil.rmtree(backup)
    if destination.exists():
        os.replace(destination, backup)
    try:
        os.replace(staging, destination)
    except Exception:
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def fetch_and_materialize(policy: dict, out: Path) -> dict:
    trusted = policy.get("trustedLeaders") or {}
    checkpoint = registry_mod.load_checkpoint(policy)
    previous_heads = checkpoint.get("heads") or {}
    if not isinstance(previous_heads, dict):
        previous_heads = {}
    accepted_heads: dict[str, dict] = {
        leader: dict(head)
        for leader, head in previous_heads.items()
        if leader in trusted and isinstance(head, dict)
    }
    snapshots: dict[str, Path] = {}
    results: dict[str, dict] = {}

    for leader, leader_policy in sorted(trusted.items()):
        if leader_policy.get("canWrite") is False:
            continue
        ipns_name = leader_policy.get("ipnsName")
        if not ipns_name:
            results[leader] = {"status": "not-enrolled"}
            continue
        previous = previous_heads.get(leader) if isinstance(previous_heads, dict) else None
        try:
            head = None
            pin_error = None
            try:
                cid = ipfs.resolve_name(policy, ipns_name)
            except Exception as ipns_error:
                try:
                    head = onion.fetch_head(policy, leader)
                    cid = head["rootCid"]
                except Exception as onion_error:
                    raise RuntimeError(
                        f"IPNS resolution failed: {ipns_error}; "
                        f"onion mirror head failed: {onion_error}"
                    ) from onion_error
            path, root, transport = _load_snapshot(policy, leader, cid)
            if head is not None and (
                head["rootSequence"] != root.get("rootSequence")
                or head.get("previousRootCid") != root.get("previousRootCid")
                or head["rootDigest"] != canonical_sha256(root)
            ):
                raise ValueError(
                    "onion mirror root does not match its signed head"
                )
            allowed, reason = _candidate_allowed(
                policy, leader, cid, root, previous, path
            )
            if not allowed:
                raise ValueError(reason)
            try:
                ipfs.pin(policy, cid)
            except Exception as error:
                if head is None and transport != "onion":
                    raise
                pin_error = str(error)
            accepted_heads[leader] = {
                "ipnsName": ipns_name,
                "cid": cid,
                "rootSequence": root["rootSequence"],
                "previousRootCid": root.get("previousRootCid"),
                "eventChainTip": root.get("eventChainTip"),
                "acceptedAt": now_utc(),
            }
            snapshots[leader] = path
            results[leader] = {
                "status": "verified",
                "cid": cid,
                "reason": reason,
                "transport": transport,
            }
            if pin_error is not None:
                results[leader]["pinError"] = pin_error
            continue
        except Exception as error:
            results[leader] = {"status": "rejected", "reason": str(error)}

        if isinstance(previous, dict) and isinstance(previous.get("cid"), str):
            try:
                path, _root, _transport = _load_snapshot(
                    policy,
                    leader,
                    previous["cid"],
                )
                try:
                    ipfs.pin(policy, previous["cid"])
                except Exception:
                    if _transport != "onion":
                        raise
                accepted_heads[leader] = previous
                snapshots[leader] = path
                results[leader]["retainedCid"] = previous["cid"]
            except Exception as error:
                results[leader]["lastGoodUnavailable"] = str(error)

    status = {
        "schema": "cluster.identity.fetch-status.v1",
        "clusterId": registry_mod.cluster_id(policy),
        "checkedAt": now_utc(),
        "leaders": results,
    }
    local_state = registry_mod.local_state_path(policy)
    write_json(local_state / "fetch-status.json", status)

    if not snapshots:
        if previous_heads:
            status["materialized"] = False
            status["retainedLastGood"] = True
            write_json(local_state / "fetch-status.json", status)
            return status
        raise RuntimeError("no trusted leader IPNS head could be accepted")

    destination = accepted_registry_path(policy)
    staging = _build_aggregate(snapshots, destination)
    try:
        registry_mod.reconcile(staging, out, policy)
        _replace_directory(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    accepted_cids = set(checkpoint.get("acceptedCids") or [])
    accepted_cids.update(head["cid"] for head in accepted_heads.values())
    registry_mod.update_checkpoint(
        policy,
        {
            "heads": accepted_heads,
            "acceptedCids": sorted(accepted_cids),
            "highestRegistryCheckpointSeen": max(
                int(checkpoint.get("highestRegistryCheckpointSeen", 0)),
                max(
                    (head["rootSequence"] for head in accepted_heads.values()),
                    default=0,
                ),
            ),
        },
    )
    apply_mod.apply_materialized(destination, out, policy)
    for leader, result in results.items():
        if result.get("status") == "verified":
            result["status"] = "accepted"
    status["materialized"] = True
    status["acceptedCids"] = sorted(head["cid"] for head in accepted_heads.values())
    write_json(local_state / "fetch-status.json", status)
    return status
