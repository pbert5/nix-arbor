from __future__ import annotations

from typing import Any

from . import db


def bucket_for_state(state: str) -> str | None:
    if state in {"created", "queued"}:
        return "queued"
    if state in {
        "waiting_for_cache",
        "waiting_for_changer",
        "waiting_for_mount",
        "needs_operator",
    }:
        return "waiting"
    if state in {
        "loading_tape",
        "mounting_ltfs",
        "running",
        "verifying",
        "updating_catalog",
        "unmounting",
        "unloading",
    }:
        return "active"
    if state == "failed":
        return "failed"
    if state == "complete":
        return "complete"
    return None


def snapshot(
    config: dict[str, Any], job_id: str, *, event_limit: int = 50
) -> dict[str, Any]:
    job = db.get_job_by_id(config, job_id)
    events_desc = db.list_job_events(config, job_id=job_id, limit=event_limit)
    events = list(reversed(events_desc))
    required_tapes = _required_tapes(job)
    copied_files = _copied_files(events)
    copied_bytes = sum(int(file.get("size_bytes") or 0) for file in copied_files)
    total_bytes = _total_bytes(job)
    total_files = _total_files(job)
    latest_event = events[-1] if events else None

    return {
        "job_id": job["id"],
        "type": job["type"],
        "state": job["state"],
        "bucket": bucket_for_state(job["state"]),
        "message": latest_event.get("message") if latest_event else None,
        "required_tapes": required_tapes,
        "blocked_tapes": _latest_blocked_tapes(events),
        "current_file": _current_file(events),
        "copied_files": copied_files,
        "copied_file_count": len(copied_files),
        "total_file_count": total_files,
        "copied_bytes": copied_bytes,
        "total_bytes": total_bytes,
        "progress_percent": _progress_percent(job["state"], copied_bytes, total_bytes),
        "job": job,
        "events": events_desc,
    }


def _required_tapes(job: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    tapes = []
    target_tape = (job.get("target") or {}).get("tape_barcode")
    if isinstance(target_tape, str) and target_tape not in seen:
        seen.add(target_tape)
        tapes.append(target_tape)
    for group in (job.get("target") or {}).get("groups", []):
        tape = group.get("tape_barcode")
        if isinstance(tape, str) and tape not in seen:
            seen.add(tape)
            tapes.append(tape)
    return tapes


def _copied_files(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    copied = []
    for event in events:
        if event["event_type"] not in {
            "retrieve_file_complete",
            "file_written",
            "file_already_present",
        }:
            continue
        data = event.get("data")
        if isinstance(data, dict):
            copied.append(data)
    return copied


def _latest_blocked_tapes(events: list[dict[str, Any]]) -> list[str]:
    for event in reversed(events):
        if event["event_type"] != "retrieve_waiting_for_mount":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            return []
        blocked = data.get("blocked_tapes")
        if isinstance(blocked, list):
            return [str(tape) for tape in blocked]
    return []


def _current_file(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    complete_count = 0
    started: dict[str, Any] | None = None
    for event in events:
        if event["event_type"] == "retrieve_file_started":
            data = event.get("data")
            started = data if isinstance(data, dict) else None
            complete_count = 0
        elif event["event_type"] == "retrieve_file_complete":
            complete_count += 1
    if started is not None and complete_count == 0:
        return started
    return None


def _total_files(job: dict[str, Any]) -> int:
    groups = (job.get("target") or {}).get("groups", [])
    if groups == []:
        return len((job.get("source") or {}).get("files", []))
    total = 0
    for group in groups:
        total += len(group.get("files", []))
    return total


def _total_bytes(job: dict[str, Any]) -> int:
    if job.get("required_bytes") is not None:
        return int(job["required_bytes"])
    groups = (job.get("target") or {}).get("groups", [])
    total = 0
    for group in groups:
        total += int(group.get("total_bytes") or 0)
    return total


def _progress_percent(state: str, copied_bytes: int, total_bytes: int) -> int:
    if state == "complete":
        return 100
    if total_bytes <= 0:
        return 0
    return min(99, int((copied_bytes / total_bytes) * 100))
