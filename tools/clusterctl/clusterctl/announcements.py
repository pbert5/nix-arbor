import base64
import binascii
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path

from . import ipfs
from .canonical import canonical_sha256
from .events import now_utc, write_json
from .registry import cluster_id, load_checkpoint, local_state_path
from .signing import key_fingerprint, sign_record, verify_signature


ANNOUNCEMENT_SCHEMA = "cluster.identity.pubsub-announcement.v1"


def _config(policy: dict) -> dict:
    return ((policy.get("registry") or {}).get("pubsub") or {})


def enabled(policy: dict) -> bool:
    registry = policy.get("registry") or {}
    transports = registry.get("transports") or {}
    return bool(transports.get("pubsub", False) and _config(policy).get("enable", False))


def topic(policy: dict) -> str:
    value = _config(policy).get("topic")
    if not isinstance(value, str) or not value:
        raise ValueError("registry PubSub topic is not configured")
    return value


def build_announcement(
    policy: dict,
    publisher_state: dict,
    root: dict,
    signing_key: Path,
) -> dict:
    leader = publisher_state.get("publisher")
    trusted = (policy.get("trustedLeaders") or {}).get(leader) or {}
    public_key = trusted.get("publicSigningKey")
    if not public_key:
        raise ValueError(f"publisher {leader!r} is not a trusted leader")
    expected_key_id = key_fingerprint(public_key)
    if root.get("publisher") != leader or root.get("publisherKeyId") != expected_key_id:
        raise ValueError("published root does not match the trusted announcement leader")
    if (
        publisher_state.get("rootCid") is None
        or publisher_state.get("rootSequence") != root.get("rootSequence")
    ):
        raise ValueError("publisher state does not match the published root")

    announcement = {
        "schema": ANNOUNCEMENT_SCHEMA,
        "clusterId": cluster_id(policy),
        "topic": topic(policy),
        "leader": leader,
        "leaderKeyId": expected_key_id,
        "ipnsName": publisher_state.get("ipnsName"),
        "rootCid": publisher_state["rootCid"],
        "rootSequence": publisher_state["rootSequence"],
        "previousRootCid": publisher_state.get("previousRootCid"),
        "rootDigest": canonical_sha256(root),
        "createdAt": now_utc(),
    }
    announcement["signature"] = sign_record(announcement, signing_key)
    return announcement


def publish_announcement(
    policy: dict,
    publisher_state: dict,
    root: dict,
    signing_key: Path,
) -> dict:
    if not enabled(policy):
        return {"status": "disabled"}
    announcement = build_announcement(policy, publisher_state, root, signing_key)
    ipfs.publish_pubsub(policy, topic(policy), announcement)
    return {
        "status": "published",
        "topic": announcement["topic"],
        "rootCid": announcement["rootCid"],
        "rootSequence": announcement["rootSequence"],
    }


def _parse_time(value: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ValueError("announcement createdAt must be a string")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("announcement createdAt must include a timezone")
    return parsed.astimezone(dt.UTC)


def validate_announcement(
    policy: dict,
    announcement: dict,
    *,
    current_time: dt.datetime | None = None,
) -> dict:
    if not isinstance(announcement, dict):
        raise ValueError("PubSub announcement must be a JSON object")
    if announcement.get("schema") != ANNOUNCEMENT_SCHEMA:
        raise ValueError(f"unsupported PubSub announcement schema {announcement.get('schema')!r}")
    if announcement.get("clusterId") != cluster_id(policy):
        raise ValueError("PubSub announcement is for another cluster")
    if announcement.get("topic") != topic(policy):
        raise ValueError("PubSub announcement topic binding does not match local policy")

    leader = announcement.get("leader")
    trusted = (policy.get("trustedLeaders") or {}).get(leader) or {}
    if not trusted or trusted.get("canWrite") is False:
        raise ValueError(f"PubSub announcement leader {leader!r} is not trusted")
    if announcement.get("ipnsName") != trusted.get("ipnsName"):
        raise ValueError("PubSub announcement IPNS name does not match trusted policy")

    cid = announcement.get("rootCid")
    if not isinstance(cid, str) or not re.fullmatch(r"[A-Za-z0-9]+", cid):
        raise ValueError("PubSub announcement contains an invalid root CID")
    sequence = announcement.get("rootSequence")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ValueError("PubSub announcement rootSequence must be a positive integer")
    previous = announcement.get("previousRootCid")
    if previous is not None and (
        not isinstance(previous, str) or not re.fullmatch(r"[A-Za-z0-9]+", previous)
    ):
        raise ValueError("PubSub announcement contains an invalid previous root CID")
    digest = announcement.get("rootDigest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("PubSub announcement contains an invalid root digest")

    created_at = _parse_time(announcement.get("createdAt"))
    now = current_time or dt.datetime.now(dt.UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.UTC)
    now = now.astimezone(dt.UTC)
    max_age = int(_config(policy).get("maxHintAgeSeconds", 600))
    max_future_skew = int(_config(policy).get("maxFutureSkewSeconds", 60))
    age = (now - created_at).total_seconds()
    if age > max_age:
        raise ValueError("PubSub announcement is stale")
    if age < -max_future_skew:
        raise ValueError("PubSub announcement creation time is too far in the future")

    ok, reason = verify_signature(
        announcement,
        policy.get("trustedLeaders") or {},
        False,
    )
    if not ok:
        raise ValueError(f"PubSub announcement signature rejected: {reason}")
    return announcement


def should_trigger(
    policy: dict,
    announcement: dict,
    checkpoint: dict | None = None,
) -> tuple[bool, str]:
    checkpoint = checkpoint if checkpoint is not None else load_checkpoint(policy)
    accepted = ((checkpoint.get("heads") or {}).get(announcement["leader"]) or {})
    accepted_sequence = accepted.get("rootSequence")
    accepted_cid = accepted.get("cid")
    if isinstance(accepted_sequence, int):
        if announcement["rootSequence"] < accepted_sequence:
            return False, "older-than-accepted-head"
        if announcement["rootSequence"] == accepted_sequence and announcement["rootCid"] == accepted_cid:
            return False, "already-accepted"
    return True, "fetch-required"


def _status_path(policy: dict) -> Path:
    return local_state_path(policy) / "pubsub-status.json"


def decode_pubsub_event(raw: str, maximum_bytes: int) -> dict:
    """Decode one newline-delimited event from ``ipfs pubsub sub --enc=json``."""
    envelope = json.loads(raw)
    if not isinstance(envelope, dict):
        raise ValueError("Kubo PubSub event must be a JSON object")
    encoded = envelope.get("data")
    if not isinstance(encoded, str) or len(encoded) < 2:
        raise ValueError("Kubo PubSub event does not contain multibase data")

    prefix, payload = encoded[0], encoded[1:]
    if prefix not in {"m", "M", "u", "U"}:
        raise ValueError(f"unsupported Kubo PubSub data multibase prefix {prefix!r}")
    if prefix in {"m", "u"}:
        payload += "=" * (-len(payload) % 4)
    altchars = b"-_" if prefix in {"u", "U"} else None
    try:
        decoded = base64.b64decode(payload, altchars=altchars, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("Kubo PubSub event contains invalid multibase data") from error
    if len(decoded) > maximum_bytes:
        raise ValueError("PubSub announcement exceeds the configured size limit")
    try:
        return json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Kubo PubSub data is not a UTF-8 JSON announcement") from error


def listen_and_trigger(
    policy: dict,
    trigger_unit: str,
    *,
    run_command=subprocess.run,
    reconnect: bool = True,
    sleep=time.sleep,
    max_subscriptions: int | None = None,
) -> None:
    if not enabled(policy):
        raise ValueError("registry PubSub listener is disabled by policy")
    selected_topic = topic(policy)
    maximum_bytes = int(_config(policy).get("maxMessageBytes", 65536))
    seen: set[str] = set()
    status = {
        "schema": "cluster.identity.pubsub-status.v1",
        "clusterId": cluster_id(policy),
        "topic": selected_topic,
        "startedAt": now_utc(),
        "accepted": 0,
        "ignored": 0,
        "rejected": 0,
        "connectionState": "connecting",
    }
    write_json(_status_path(policy), status)

    subscriptions = 0
    while max_subscriptions is None or subscriptions < max_subscriptions:
        subscriptions += 1
        try:
            process = ipfs.subscribe_pubsub(policy, selected_topic)
            status["connectionState"] = "subscribed"
            status.pop("lastConnectionError", None)
            write_json(_status_path(policy), status)

            assert process.stdout is not None
            for raw in process.stdout:
                status["lastMessageAt"] = now_utc()
                try:
                    announcement = validate_announcement(
                        policy,
                        decode_pubsub_event(raw, maximum_bytes),
                    )
                    digest = canonical_sha256(announcement)
                    if digest in seen:
                        status["ignored"] += 1
                        status["lastResult"] = "duplicate-announcement"
                        write_json(_status_path(policy), status)
                        continue
                    seen.add(digest)
                    trigger, reason = should_trigger(policy, announcement)
                    if not trigger:
                        status["ignored"] += 1
                        status["lastResult"] = reason
                        write_json(_status_path(policy), status)
                        continue
                    run_command(
                        ["systemctl", "start", "--no-block", trigger_unit],
                        check=True,
                    )
                    status["accepted"] += 1
                    status["lastResult"] = "fetch-triggered"
                    status["lastLeader"] = announcement["leader"]
                    status["lastRootCid"] = announcement["rootCid"]
                    status["lastRootSequence"] = announcement["rootSequence"]
                except Exception as error:
                    status["rejected"] += 1
                    status["lastResult"] = "rejected"
                    status["lastError"] = str(error)
                write_json(_status_path(policy), status)

            return_code = process.wait()
            if not reconnect and return_code == 0:
                return
            connection_error = RuntimeError(
                f"Kubo PubSub subscription exited with status {return_code}"
            )
        except Exception as error:
            connection_error = error

        if not reconnect:
            raise connection_error
        status["connectionState"] = "retrying"
        status["lastConnectionError"] = str(connection_error)
        write_json(_status_path(policy), status)
        if max_subscriptions is not None and subscriptions >= max_subscriptions:
            return
        sleep(int(_config(policy).get("reconnectDelaySeconds", 5)))
