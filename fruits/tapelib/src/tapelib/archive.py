"""archive.py — staging and write-to-tape support for tapelib.

This module owns the two-phase write path:

  1. ``stage_games_archive``: copy source files to the local cache, compute
      checksums, and queue one or more ``write_archive`` DB jobs that fit the
      currently available cache budget.

  2. ``write_staged_archive``: given a queued ``write_archive`` job, copy the
     staged files onto a mounted read-write LTFS tape, write self-describing
     manifests, and update the catalog.

The caller is always responsible for ensuring the target tape is mounted
read-write before calling ``write_staged_archive``; this module never moves
the robot arm or calls ``ltfs`` itself.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

from . import db

WRITE_ARCHIVE_JOB_TYPE = "write_archive"
BUNDLE_MANIFEST_FORMAT = "tapelib-tar-bundle-v1"
BUNDLE_MANIFEST_SUFFIX = ".members.json"
BUNDLE_DIRECTORY_NAME = "_tapelib-bundles"
DEFAULT_SMALL_FILE_BUNDLE_MAX_BYTES = 0
DEFAULT_SMALL_FILE_BUNDLE_TARGET_BYTES = 256 * 1024 * 1024
INTERNAL_TAPE_FILES = {
    "TAPELIB-INVENTORY.json",
    "TAPE-MANIFEST.json",
    "TAPE-MANIFEST.csv",
    "TAPE-CHECKSUMS.sha256",
    "README-THIS-TAPE.txt",
}


class ArchiveError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _checksum_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_root(config: dict[str, Any]) -> Path:
    return Path(config.get("cache", {}).get("path", "/run/media/ash/cache/tapelib"))


def _parse_size_string(value: str | int | float | None) -> int:
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    suffixes = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    text = str(value).strip()
    if text[-1].upper() in suffixes:
        return int(float(text[:-1]) * suffixes[text[-1].upper()])
    return int(text)


def _tree_size_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    total = 0
    for path in root.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
    return total


def _bundle_settings(config: dict[str, Any]) -> tuple[int, int]:
    archive_cfg = config.get("archive", {})
    max_small_file_bytes = _parse_size_string(
        archive_cfg.get("smallFileBundleMaxBytes", DEFAULT_SMALL_FILE_BUNDLE_MAX_BYTES)
    )
    bundle_target_bytes = _parse_size_string(
        archive_cfg.get("smallFileBundleTargetBytes", DEFAULT_SMALL_FILE_BUNDLE_TARGET_BYTES)
    )
    return max_small_file_bytes, bundle_target_bytes


def _available_cache_bytes(config: dict[str, Any]) -> int:
    cache_root = _cache_root(config)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_cfg = config.get("cache", {})
    stat = os.statvfs(cache_root)
    free_bytes = stat.f_bavail * stat.f_frsize
    reserved_free = _parse_size_string(cache_cfg.get("reservedFreeBytes", 0))
    max_bytes = _parse_size_string(cache_cfg.get("maxBytes", 0))
    fs_budget = max(0, free_bytes - reserved_free)
    if max_bytes <= 0:
        return fs_budget
    used_bytes = _tree_size_bytes(cache_root)
    logical_budget = max(0, max_bytes - used_bytes)
    return max(0, min(fs_budget, logical_budget))


def _is_mounted_rw(path: str) -> bool:
    """Return True if *path* is an active read-write mount."""
    result = subprocess.run(
        ["findmnt", "-n", "--output", "OPTIONS", "--target", path],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    options = {opt.strip() for opt in result.stdout.strip().split(",") if opt.strip()}
    return "rw" in options


def _tape_id_from_barcode(
    connection: "sqlite3.Connection",  # type: ignore[name-defined]
    barcode: str,
) -> int | None:
    row = connection.execute(
        "SELECT id FROM tapes WHERE barcode = ?", (barcode,)
    ).fetchone()
    return None if row is None else row["id"]


def _existing_write_targets(config: dict[str, Any]) -> set[tuple[str, str]]:
    existing: set[tuple[str, str]] = set()

    for file_row in db.list_files(config):
        state = file_row.get("state")
        if state not in {"missing_after_reindex", "read_error"}:
            existing.add((file_row["tape_barcode"], file_row["path"].removeprefix("games/")))

    for bundle_row in db.list_bundle_members(config):
        existing.add(
            (
                bundle_row["tape_barcode"],
                bundle_row["member_path"].removeprefix("games/"),
            )
        )

    for job in db.list_jobs(config, limit=5000):
        if job["type"] != WRITE_ARCHIVE_JOB_TYPE:
            continue
        if job["state"] in {"failed", "cancelled"}:
            continue
        tape_barcode = (job.get("target") or {}).get("tape_barcode")
        if not isinstance(tape_barcode, str):
            continue
        for staged_file in (job.get("source") or {}).get("files", []):
            logical_path = staged_file.get("logical_path")
            if isinstance(logical_path, str):
                existing.add((tape_barcode, logical_path))
    return existing


def _clone_assignment_with_files(
    assignment: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    cache_split_part: int = 1,
    cache_split_enabled: bool = False,
) -> dict[str, Any]:
    cloned = dict(assignment)
    cloned["files"] = [dict(file_entry) for file_entry in files]
    cloned["size_bytes"] = sum(int(file_entry["size_bytes"]) for file_entry in files)
    cloned["cache_split"] = {
        "enabled": cache_split_enabled,
        "part": cache_split_part,
    }
    return cloned


def _pending_assignments(
    config: dict[str, Any],
    plan: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    existing_targets = _existing_write_targets(config)
    pending: list[dict[str, Any]] = []
    skipped_files = 0
    skipped_bytes = 0

    for assignment in plan.get("assignments", []):
        tape_barcode = assignment["tape"]
        remaining_files: list[dict[str, Any]] = []
        for file_entry in assignment.get("files", []):
            logical_path = file_entry["logical_path"]
            if (tape_barcode, logical_path) in existing_targets:
                skipped_files += 1
                skipped_bytes += int(file_entry.get("size_bytes") or 0)
                continue
            remaining_files.append(dict(file_entry))
        if remaining_files:
            pending.append(_clone_assignment_with_files(assignment, remaining_files))

    return pending, {
        "skipped_existing_files": skipped_files,
        "skipped_existing_bytes": skipped_bytes,
    }


def _slice_assignments_to_budget(
    assignments: list[dict[str, Any]],
    budget_bytes: int,
) -> tuple[list[dict[str, Any]], int]:
    if budget_bytes <= 0:
        return [], 0

    selected: list[dict[str, Any]] = []
    selected_bytes = 0

    for assignment in assignments:
        assignment_size = int(assignment.get("size_bytes") or 0)
        remaining_budget = budget_bytes - selected_bytes
        if assignment_size <= remaining_budget:
            selected.append(_clone_assignment_with_files(assignment, assignment.get("files", [])))
            selected_bytes += assignment_size
            if selected_bytes >= budget_bytes:
                break
            continue

        partial_files: list[dict[str, Any]] = []
        partial_bytes = 0
        partial_index = 1
        for file_entry in assignment.get("files", []):
            file_size = int(file_entry.get("size_bytes") or 0)
            if file_size > budget_bytes:
                raise ArchiveError(
                    f"File exceeds the configured staging budget and cannot be chunked safely: {file_entry['source_path']}"
                )
            if partial_bytes + file_size > remaining_budget:
                break
            partial_files.append(dict(file_entry))
            partial_bytes += file_size

        if partial_files:
            selected.append(
                _clone_assignment_with_files(
                    assignment,
                    partial_files,
                    cache_split_enabled=True,
                    cache_split_part=partial_index,
                )
            )
            selected_bytes += partial_bytes
        break

    return selected, selected_bytes


def _group_assignments_into_batches(
    assignments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    batches: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for assignment in assignments:
        tape_barcode = assignment["tape"]
        if current is None or current["tape_barcode"] != tape_barcode:
            current = {
                "tape_barcode": tape_barcode,
                "assignments": [],
                "size_bytes": 0,
            }
            batches.append(current)
        current["assignments"].append(assignment)
        current["size_bytes"] += int(assignment.get("size_bytes") or 0)

    return batches


def _plan_bundle_groups(
    bundle_candidates: list[dict[str, Any]],
    bundle_target_bytes: int,
) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    if bundle_target_bytes <= 0:
        return [], bundle_candidates

    groups: list[list[dict[str, Any]]] = []
    leftovers: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_bytes = 0

    for candidate in bundle_candidates:
        size_bytes = int(candidate.get("size_bytes") or 0)
        if size_bytes > bundle_target_bytes:
            leftovers.append(candidate)
            continue
        if current and current_bytes + size_bytes > bundle_target_bytes:
            if len(current) >= 2:
                groups.append(current)
            else:
                leftovers.extend(current)
            current = []
            current_bytes = 0
        current.append(candidate)
        current_bytes += size_bytes

    if current:
        if len(current) >= 2:
            groups.append(current)
        else:
            leftovers.extend(current)

    return groups, leftovers


def _stage_bundle_write_units(
    staging_dir: Path,
    namespace_prefix: str,
    bundle_index: int,
    members: list[dict[str, Any]],
    *,
    generated_at: str | None,
) -> list[dict[str, Any]]:
    bundle_root = staging_dir / BUNDLE_DIRECTORY_NAME
    bundle_root.mkdir(parents=True, exist_ok=True)
    bundle_name = f"bundle-{bundle_index:04d}"
    bundle_relative_path = f"{BUNDLE_DIRECTORY_NAME}/{bundle_name}.tar"
    manifest_relative_path = f"{BUNDLE_DIRECTORY_NAME}/{bundle_name}{BUNDLE_MANIFEST_SUFFIX}"
    bundle_path = staging_dir / bundle_relative_path
    manifest_path = staging_dir / manifest_relative_path

    manifest_members: list[dict[str, Any]] = []
    with tarfile.open(bundle_path, mode="w") as tar_handle:
        for member in members:
            source_path = Path(member["source_path"])
            checksum = _checksum_sha256(source_path)
            member["checksum_sha256"] = checksum
            member_path = f"{namespace_prefix}/{member['logical_path']}"
            member["member_path"] = member_path
            tar_handle.add(source_path, arcname=member_path)
            manifest_members.append(
                {
                    "member_path": member_path,
                    "logical_path": member["logical_path"],
                    "size_bytes": member["size_bytes"],
                    "checksum_sha256": checksum,
                }
            )

    manifest = {
        "format": BUNDLE_MANIFEST_FORMAT,
        "generated_at": generated_at or _utc_now(),
        "bundle_path": f"{namespace_prefix}/{bundle_relative_path}",
        "member_count": len(manifest_members),
        "members": manifest_members,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return [
        {
            "kind": "bundle",
            "source_path": f"bundle://{namespace_prefix}/{bundle_relative_path}",
            "logical_path": bundle_relative_path,
            "staging_path": str(bundle_path),
            "size_bytes": bundle_path.stat().st_size,
            "checksum_sha256": _checksum_sha256(bundle_path),
            "members": manifest_members,
        },
        {
            "kind": "bundle_manifest",
            "source_path": f"bundle-manifest://{namespace_prefix}/{manifest_relative_path}",
            "logical_path": manifest_relative_path,
            "staging_path": str(manifest_path),
            "size_bytes": manifest_path.stat().st_size,
            "checksum_sha256": _checksum_sha256(manifest_path),
            "bundle_path": f"{namespace_prefix}/{bundle_relative_path}",
            "members": manifest_members,
        },
    ]


def _library_inventory_manifest(config: dict[str, Any]) -> dict[str, Any]:
    db.initialize_database(config)
    return {
        "format": "tapelib-library-inventory-v1",
        "generated_at": _utc_now(),
        "conflict_policy": {
            "mode": "additive_latest_observation_wins",
            "notes": (
                "Tape-carried manifests are advisory snapshots. Importing an older "
                "manifest must not delete or downgrade newer catalog data."
            ),
        },
        "tapes": db.list_tapes(config, include_ignored=True),
        "drives": db.list_drives(config),
        "files": db.list_files(config),
    }


def _merge_cleanup_summaries(*summaries: dict[str, Any]) -> dict[str, Any]:
    staging_dir = ""
    removed_files = 0
    removed_bytes = 0
    for summary in summaries:
        if not staging_dir:
            staging_dir = str(summary.get("staging_dir") or "")
        removed_files += int(summary.get("removed_files") or 0)
        removed_bytes += int(summary.get("removed_bytes") or 0)
    return {
        "staging_dir": staging_dir,
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
    }


def _consume_staged_file(
    config: dict[str, Any],
    job_id: str,
    staged_file: dict[str, Any],
) -> dict[str, Any]:
    staging_path = Path(staged_file.get("staging_path", ""))
    removed_files = 0
    removed_bytes = 0

    if staging_path.is_file():
        removed_bytes = staging_path.stat().st_size
        removed_files = 1
        staging_path.unlink(missing_ok=True)

    with closing(db.connect(config)) as connection:
        with connection:
            connection.execute(
                """
                UPDATE cache_entries
                SET state = 'consumed'
                WHERE job_id = ? AND cache_path = ? AND state = 'staged'
                """,
                (job_id, str(staging_path)),
            )

    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "staging_dir": str(Path(staged_file.get("staging_path", "")).parent),
    }


def _validate_against_library_catalog(
    config: dict[str, Any],
    tape_barcode: str,
    tape_path: str,
    *,
    size_bytes: int,
    checksum_sha256: str,
) -> None:
    catalog_row = db.get_file(config, tape_barcode=tape_barcode, path=tape_path)
    if catalog_row is None:
        return

    catalog_size = catalog_row.get("size_bytes")
    if catalog_size is not None and int(catalog_size) != int(size_bytes):
        raise ArchiveError(
            "Library catalog disagrees with the already-written LTFS file size for "
            f"{tape_barcode}:{tape_path}"
        )

    catalog_checksum = catalog_row.get("checksum_sha256")
    if catalog_checksum and catalog_checksum != checksum_sha256:
        raise ArchiveError(
            "Library catalog disagrees with the already-written LTFS checksum for "
            f"{tape_barcode}:{tape_path}"
        )


# ---------------------------------------------------------------------------
# Phase 1 — stage files to local cache
# ---------------------------------------------------------------------------


def stage_games_archive(
    config: dict[str, Any],
    plan: dict[str, Any],
    *,
    max_staged_bytes: int | None = None,
) -> list[dict[str, Any]]:
    """Stage all files in *plan* to the local cache.

    *plan* is the dict returned by ``_plan_game_backup`` / the
    ``plan-games-backup`` CLI command.  One ``write_archive`` DB job is
    created per target tape.  Returns the list of created jobs (already
    stored in the DB).

    Raises :class:`ArchiveError` if a source file is missing or a copy
    fails.  Partial staging state is left in place so the operator can
    inspect it; the DB job is not created for tapes that failed to stage
    completely.
    """
    db.initialize_database(config)
    staging_root = _cache_root(config) / "staging" / "archive-jobs"
    namespace_prefix = plan.get("namespace_prefix", "/games").strip("/")

    # Group assignments by tape barcode.
    tape_assignments: dict[str, list[dict[str, Any]]] = {}
    for assignment in plan.get("assignments", []):
        tape = assignment["tape"]
        tape_assignments.setdefault(tape, []).append(assignment)

    if not tape_assignments:
        raise ArchiveError("Plan contains no tape assignments to stage.")

    pending_assignments, pending_summary = _pending_assignments(config, plan)
    if not pending_assignments:
        return []

    budget_bytes = (
        _available_cache_bytes(config)
        if max_staged_bytes is None
        else max_staged_bytes
    )
    if budget_bytes <= 0:
        raise ArchiveError("No cache budget is currently available for staging.")

    selected_assignments, selected_bytes = _slice_assignments_to_budget(
        pending_assignments,
        budget_bytes,
    )
    if not selected_assignments:
        raise ArchiveError(
            "No pending files fit inside the current cache budget. "
            "Free cache space or increase the staging budget."
        )

    batches = _group_assignments_into_batches(selected_assignments)
    created_jobs: list[dict[str, Any]] = []
    max_small_file_bytes, bundle_target_bytes = _bundle_settings(config)

    for batch_index, batch in enumerate(batches, start=1):
        tape_barcode = batch["tape_barcode"]
        assignments = batch["assignments"]
        job_id = str(uuid.uuid4())
        staging_dir = staging_root / job_id / tape_barcode
        staging_dir.mkdir(parents=True, exist_ok=True)

        staged_files: list[dict[str, Any]] = []
        write_units: list[dict[str, Any]] = []
        total_bytes = 0
        bundle_candidates: list[dict[str, Any]] = []
        bundle_index = 1

        for assignment in assignments:
            for planned_file in assignment.get("files", []):
                source_path = Path(planned_file["source_path"])
                logical_path = planned_file["logical_path"]

                if not source_path.exists():
                    raise ArchiveError(
                        f"Source file not found: {source_path}"
                    )

                logical_file = {
                    "source_path": str(source_path),
                    "logical_path": logical_path,
                    "size_bytes": int(planned_file["size_bytes"]),
                }
                staged_files.append(logical_file)
                total_bytes += logical_file["size_bytes"]

                if (
                    max_small_file_bytes > 0
                    and logical_file["size_bytes"] <= max_small_file_bytes
                ):
                    bundle_candidates.append(logical_file)
                    continue

                staging_path = staging_dir / logical_path
                staging_path.parent.mkdir(parents=True, exist_ok=True)

                # Copy via temp file → atomic rename.
                staging_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path = staging_path.with_name(
                    f".{staging_path.name}.staging-{uuid.uuid4().hex}.tmp"
                )
                try:
                    shutil.copy2(source_path, temp_path)
                    os.replace(temp_path, staging_path)
                except OSError as exc:
                    try:
                        temp_path.unlink(missing_ok=True)
                    except OSError:
                        pass
                    raise ArchiveError(
                        f"Failed staging {source_path} → {staging_path}: {exc}"
                    ) from exc

                checksum = _checksum_sha256(staging_path)
                size_bytes = staging_path.stat().st_size
                logical_file["checksum_sha256"] = checksum
                logical_file["staging_path"] = str(staging_path)
                write_units.append(
                    {
                        "kind": "file",
                        "source_path": str(source_path),
                        "logical_path": logical_path,
                        "staging_path": str(staging_path),
                        "size_bytes": size_bytes,
                        "checksum_sha256": checksum,
                    }
                )

        bundle_groups, leftover_small_files = _plan_bundle_groups(
            bundle_candidates,
            bundle_target_bytes,
        )

        for leftover in leftover_small_files:
            source_path = Path(leftover["source_path"])
            staging_path = staging_dir / leftover["logical_path"]
            staging_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = staging_path.with_name(
                f".{staging_path.name}.staging-{uuid.uuid4().hex}.tmp"
            )
            try:
                shutil.copy2(source_path, temp_path)
                os.replace(temp_path, staging_path)
            except OSError as exc:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
                raise ArchiveError(
                    f"Failed staging {source_path} → {staging_path}: {exc}"
                ) from exc

            checksum = _checksum_sha256(staging_path)
            leftover["checksum_sha256"] = checksum
            leftover["staging_path"] = str(staging_path)
            write_units.append(
                {
                    "kind": "file",
                    "source_path": str(source_path),
                    "logical_path": leftover["logical_path"],
                    "staging_path": str(staging_path),
                    "size_bytes": staging_path.stat().st_size,
                    "checksum_sha256": checksum,
                }
            )

        for members in bundle_groups:
            write_units.extend(
                _stage_bundle_write_units(
                    staging_dir,
                    namespace_prefix,
                    bundle_index,
                    members,
                    generated_at=plan.get("generated_at"),
                )
            )
            bundle_path = f"{namespace_prefix}/{BUNDLE_DIRECTORY_NAME}/bundle-{bundle_index:04d}.tar"
            for member in members:
                member["bundled_in"] = bundle_path
            bundle_index += 1

        source_payload = {
            "kind": "staged_games_archive",
            "staging_dir": str(staging_dir),
            "plan_generated_at": plan.get("generated_at"),
            "namespace_prefix": namespace_prefix,
            "batch_index": batch_index,
            "batch_count": len(batches),
            "batch_bytes": total_bytes,
            "budget_bytes": budget_bytes,
            "selected_bytes": selected_bytes,
            "skipped_existing_files": pending_summary["skipped_existing_files"],
            "skipped_existing_bytes": pending_summary["skipped_existing_bytes"],
            "files": staged_files,
            "write_units": write_units,
        }
        target_payload = {
            "tape_barcode": tape_barcode,
            "namespace_prefix": namespace_prefix,
        }

        with closing(db.connect(config)) as connection:
            with connection:
                tape_id = _tape_id_from_barcode(connection, tape_barcode)
                job = db.create_job_with_connection(
                    connection,
                    WRITE_ARCHIVE_JOB_TYPE,
                    state="queued",
                    source=source_payload,
                    target=target_payload,
                    required_bytes=total_bytes,
                    assigned_tape_id=tape_id,
                )
                now = _utc_now()
                for staged_file in write_units:
                    connection.execute(
                        """
                        INSERT INTO cache_entries (
                          job_id, source_path, cache_path, size_bytes,
                          checksum_sha256, state, created_at
                        ) VALUES (?, ?, ?, ?, ?, 'staged', ?)
                        """,
                        (
                            job["id"],
                            staged_file["source_path"],
                            staged_file["staging_path"],
                            staged_file["size_bytes"],
                            staged_file["checksum_sha256"],
                            now,
                        ),
                    )

        created_jobs.append(job)

    return created_jobs


# ---------------------------------------------------------------------------
# Phase 2 — write staged archive to mounted LTFS tape
# ---------------------------------------------------------------------------


def write_staged_archive(
    config: dict[str, Any],
    job: dict[str, Any],
    *,
    resume: bool = False,
) -> dict[str, Any]:
    """Write a staged ``write_archive`` job's files to tape.

    The target tape **must** already be mounted read-write at its configured
    mount path.  This function never moves the robot arm or mounts LTFS.

    Steps:
    1. Validate job state and staging directory.
    2. Write each file via ``{mount}/.tapelib-writing/{job_id}/{logical}``
       temp path, then rename to ``{mount}/{namespace}/{logical}``.
    3. Write self-describing manifest files at the tape root.
    4. Upsert catalog ``files`` rows.
    5. Mark job complete.

    Raises :class:`ArchiveError` on any failure; the job is marked ``failed``
    and the tape may contain partial data — the operator should inspect it.
    """
    if job["type"] != WRITE_ARCHIVE_JOB_TYPE:
        raise ArchiveError(
            f"Job {job['id']} is type {job['type']!r}, not {WRITE_ARCHIVE_JOB_TYPE!r}."
        )
    runnable_states = {"queued", "waiting_for_mount"}
    if resume:
        runnable_states |= {"failed", "needs_operator"}
    if job["state"] not in runnable_states:
        raise ArchiveError(
            f"Job {job['id']} is in state {job['state']!r}; "
            f"must be one of {sorted(runnable_states)} to write."
        )

    source = job.get("source") or {}
    target = job.get("target") or {}
    tape_barcode: str = target.get("tape_barcode", "")
    namespace_prefix: str = source.get("namespace_prefix", "games").strip("/")
    staging_dir = Path(source.get("staging_dir", ""))
    files: list[dict[str, Any]] = source.get("files", [])
    write_units: list[dict[str, Any]] = source.get("write_units") or files

    if not tape_barcode:
        raise ArchiveError(
            f"write_archive job {job['id']} is missing target.tape_barcode."
        )
    if not staging_dir.is_dir():
        raise ArchiveError(
            f"Staging directory not found for job {job['id']}: {staging_dir}"
        )

    mount_path = _find_tape_mount_path(config, tape_barcode)
    if mount_path is None:
        with closing(db.connect(config)) as connection:
            with connection:
                db.transition_job(
                    connection,
                    job["id"],
                    "waiting_for_mount",
                    event_type="write_archive_waiting",
                    message=(
                        "Target tape is not mounted read-write. "
                        "Load and mount the tape, then re-run write-archive."
                    ),
                    data={"tape_barcode": tape_barcode},
                )
        raise ArchiveError(
            f"Tape {tape_barcode!r} is not mounted. "
            "Load it (tapelib load-tape) and mount it read-write "
            "(tapelib mount-ltfs --read-write), then retry."
        )

    mount_root = Path(mount_path)
    job_temp_dir = mount_root / ".tapelib-writing" / job["id"]
    resumed = resume and job["state"] in {"failed", "needs_operator"}

    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job["id"],
                "running",
                event_type=(
                    "write_archive_resumed" if resumed else "write_archive_started"
                ),
                message=(
                    "Resuming staged archive write to LTFS tape."
                    if resumed
                    else "Writing staged archive files to LTFS tape."
                ),
                data={
                    "tape_barcode": tape_barcode,
                    "mount_path": mount_path,
                    "file_count": len(files),
                    "resume": resumed,
                },
            )

    try:
        job_temp_dir.mkdir(parents=True, exist_ok=True)

        written_files: list[dict[str, Any]] = []
        cache_cleanup_summary = {
            "removed_files": 0,
            "removed_bytes": 0,
            "staging_dir": str(staging_dir),
        }

        for staged_file in write_units:
            logical_path: str = staged_file["logical_path"]
            staging_path = Path(staged_file["staging_path"])
            expected_checksum: str | None = staged_file.get("checksum_sha256")
            unit_kind = staged_file.get("kind", "file")

            # Use temp path inside .tapelib-writing while writing.
            temp_path = job_temp_dir / logical_path
            final_path = mount_root / namespace_prefix / logical_path

            temp_path.parent.mkdir(parents=True, exist_ok=True)
            final_path.parent.mkdir(parents=True, exist_ok=True)

            tape_relative = f"{namespace_prefix}/{logical_path}"
            reused_existing = False

            if final_path.exists():
                actual_checksum = _checksum_sha256(final_path)
                if expected_checksum and actual_checksum != expected_checksum:
                    raise ArchiveError(
                        "Target path already exists on tape with different "
                        f"contents: {tape_relative}"
                    )
                _validate_against_library_catalog(
                    config,
                    tape_barcode,
                    tape_relative,
                    size_bytes=int(staged_file["size_bytes"]),
                    checksum_sha256=actual_checksum,
                )
                reused_existing = True
            else:
                if not staging_path.is_file():
                    raise ArchiveError(
                        f"Staged file is missing (was it cleaned up?): {staging_path}"
                    )

                temp_path.unlink(missing_ok=True)
                shutil.copy2(staging_path, temp_path)

                actual_checksum = _checksum_sha256(temp_path)
                if expected_checksum and actual_checksum != expected_checksum:
                    temp_path.unlink(missing_ok=True)
                    raise ArchiveError(
                        f"Checksum mismatch for {logical_path}: "
                        f"expected {expected_checksum}, got {actual_checksum}"
                    )

                os.replace(temp_path, final_path)

            physical_entry = {
                "logical_path": logical_path,
                "tape_path": tape_relative,
                "size_bytes": staged_file["size_bytes"],
                "checksum_sha256": actual_checksum,
            }
            written_files.append(physical_entry)

            _update_catalog(config, tape_barcode, namespace_prefix, [physical_entry])
            if unit_kind == "bundle":
                _upsert_bundle_preview_catalog(
                    config,
                    tape_barcode,
                    tape_relative,
                    staged_file.get("members", []),
                )
            cache_cleanup_summary = _merge_cleanup_summaries(
                cache_cleanup_summary,
                _consume_staged_file(config, job["id"], staged_file),
            )

            with closing(db.connect(config)) as connection:
                with connection:
                    if unit_kind == "bundle":
                        db.append_job_event(
                            connection,
                            job["id"],
                            "bundle_written",
                            (
                                f"Already present on tape; reused bundled archive: {tape_relative}"
                                if reused_existing
                                else f"Written bundled archive to tape: {tape_relative}"
                            ),
                            {
                                "bundle_path": tape_relative,
                                "member_count": len(staged_file.get("members", [])),
                                "tape_barcode": tape_barcode,
                                "resumed": reused_existing,
                            },
                        )
                        for member in staged_file.get("members", []):
                            db.append_job_event(
                                connection,
                                job["id"],
                                (
                                    "file_already_present"
                                    if reused_existing
                                    else "file_written"
                                ),
                                (
                                    f"Already present in bundle; resumed without rewriting: {member['member_path']}"
                                    if reused_existing
                                    else f"Written to tape via bundle: {member['member_path']}"
                                ),
                                {
                                    "logical_path": member["logical_path"],
                                    "tape_path": member["member_path"],
                                    "size_bytes": member["size_bytes"],
                                    "checksum_sha256": member.get("checksum_sha256"),
                                    "tape_barcode": tape_barcode,
                                    "resumed": reused_existing,
                                    "bundled_in": tape_relative,
                                },
                            )
                    elif unit_kind == "bundle_manifest":
                        db.append_job_event(
                            connection,
                            job["id"],
                            "bundle_manifest_written",
                            (
                                f"Already present on tape; reused bundle manifest: {tape_relative}"
                                if reused_existing
                                else f"Written bundle manifest to tape: {tape_relative}"
                            ),
                            {
                                "tape_path": tape_relative,
                                "size_bytes": staged_file["size_bytes"],
                                "checksum_sha256": actual_checksum,
                                "tape_barcode": tape_barcode,
                                "resumed": reused_existing,
                            },
                        )
                    else:
                        db.append_job_event(
                            connection,
                            job["id"],
                            (
                                "file_already_present"
                                if reused_existing
                                else "file_written"
                            ),
                            (
                                f"Already present on tape; resumed without rewriting: {tape_relative}"
                                if reused_existing
                                else f"Written to tape: {tape_relative}"
                            ),
                            {
                                "logical_path": logical_path,
                                "tape_path": tape_relative,
                                "size_bytes": staged_file["size_bytes"],
                                "checksum_sha256": actual_checksum,
                                "tape_barcode": tape_barcode,
                                "resumed": reused_existing,
                            },
                        )

        # Remove .tapelib-writing/{job_id} dir if empty.
        _try_rmdir(job_temp_dir)
        _try_rmdir(mount_root / ".tapelib-writing")

        # Write self-describing manifests at the tape root, aggregating prior
        # batches already present on the tape.
        _write_tape_manifests(
            config,
            mount_root,
            tape_barcode,
            job["id"],
            namespace_prefix,
        )

        cleanup_summary = _merge_cleanup_summaries(
            cache_cleanup_summary,
            cleanup_staged_job_cache(config, job),
        )

        with closing(db.connect(config)) as connection:
            with connection:
                db.transition_job(
                    connection,
                    job["id"],
                    "complete",
                    event_type="write_archive_complete",
                    message="Archive written to tape and catalog updated.",
                    data={
                        "written_files": len(written_files),
                        "tape_barcode": tape_barcode,
                        "cleanup": cleanup_summary,
                    },
                )
            return db.get_job(connection, job["id"])

    except Exception:
        with closing(db.connect(config)) as connection:
            with connection:
                db.transition_job(
                    connection,
                    job["id"],
                    "failed",
                    event_type="write_archive_failed",
                    message=(
                        "Archive write failed; tape may contain partial data. "
                        "Check the journal and inspect the tape before retrying."
                    ),
                    data={"tape_barcode": tape_barcode},
                )
        raise


# ---------------------------------------------------------------------------
# Mount-path resolution
# ---------------------------------------------------------------------------


def _find_tape_mount_path(
    config: dict[str, Any], tape_barcode: str
) -> str | None:
    """Return the mount_path of the drive that has *tape_barcode* loaded and
    LTFS-mounted, or ``None`` if not found / not mounted."""
    tape_by_id = {
        tape["id"]: tape["barcode"]
        for tape in db.list_tapes(config, include_ignored=True)
        if tape.get("id") is not None
    }
    for drive in db.list_drives(config):
        barcode = tape_by_id.get(drive.get("loaded_tape_id"))
        if barcode != tape_barcode:
            continue
        mount_path = drive.get("mount_path")
        if not mount_path:
            continue
        if _is_mounted_rw(mount_path):
            return mount_path
    return None


# ---------------------------------------------------------------------------
# Manifest writers
# ---------------------------------------------------------------------------


def _write_tape_manifests(
    config: dict[str, Any],
    mount_root: Path,
    tape_barcode: str,
    job_id: str,
    namespace_prefix: str,
) -> None:
    now = _utc_now()
    catalog_files = db.list_files(config, tape_barcode=tape_barcode)
    manifest_files = [
        {
            "logical_path": file_row["path"].removeprefix(f"{namespace_prefix}/"),
            "tape_path": file_row["path"],
            "size_bytes": file_row.get("size_bytes"),
            "checksum_sha256": file_row.get("checksum_sha256"),
            "state": file_row.get("state"),
        }
        for file_row in catalog_files
    ]
    checksum_lines = [
        f"{file_row['checksum_sha256']}  {file_row['path']}"
        for file_row in catalog_files
        if file_row.get("checksum_sha256")
    ]

    manifest: dict[str, Any] = {
        "format": "tapelib-tape-manifest-v1",
        "tape_barcode": tape_barcode,
        "written_at": now,
        "job_id": job_id,
        "namespace_prefix": f"/{namespace_prefix}",
        "file_count": len(manifest_files),
        "files": manifest_files,
    }
    (mount_root / "TAPE-MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    csv_lines = ["tape_path,size_bytes,checksum_sha256"]
    for f in manifest_files:
        csv_lines.append(
            f"{f['tape_path']},{f['size_bytes']},{f['checksum_sha256']}"
        )
    (mount_root / "TAPE-MANIFEST.csv").write_text(
        "\n".join(csv_lines) + "\n", encoding="utf-8"
    )

    (mount_root / "TAPE-CHECKSUMS.sha256").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8"
    )

    readme = "\n".join(
        [
            f"TAPELIB ARCHIVE TAPE: {tape_barcode}",
            f"Written: {now}",
            f"Job ID: {job_id}",
            f"Namespace: /{namespace_prefix}",
            f"Files: {len(manifest_files)}",
            "",
            "This tape was written by tapelib.",
            f"Files are located under /{namespace_prefix}/ on this tape.",
            "",
            "TAPE-MANIFEST.json    — machine-readable file list",
            "TAPE-MANIFEST.csv     — CSV file list",
            "TAPE-CHECKSUMS.sha256 — SHA-256 checksums for all files",
            "TAPELIB-INVENTORY.json — additive library inventory snapshot",
            "",
            "To verify: sha256sum -c TAPE-CHECKSUMS.sha256",
            "To catalog: tapelib index-tape <barcode|drive>",
            "To import inventory: tapelib import-inventory <path>",
        ]
    )
    (mount_root / "README-THIS-TAPE.txt").write_text(
        readme + "\n", encoding="utf-8"
    )

    (mount_root / "TAPELIB-INVENTORY.json").write_text(
        json.dumps(_library_inventory_manifest(config), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Catalog update
# ---------------------------------------------------------------------------


def _update_catalog(
    config: dict[str, Any],
    tape_barcode: str,
    namespace_prefix: str,
    written_files: list[dict[str, Any]],
) -> None:
    now = _utc_now()
    with closing(db.connect(config)) as connection:
        with connection:
            tape_id = db.get_or_create_tape(connection, tape_barcode)
            for f in written_files:
                connection.execute(
                    """
                    INSERT INTO files (
                      tape_id, path, logical_group, size_bytes,
                      checksum_sha256, state, indexed_at
                    )
                    VALUES (?, ?, ?, ?, ?, 'verified', ?)
                    ON CONFLICT(tape_id, path) DO UPDATE SET
                      size_bytes        = excluded.size_bytes,
                      checksum_sha256   = excluded.checksum_sha256,
                      logical_group     = excluded.logical_group,
                      state             = excluded.state,
                      indexed_at        = excluded.indexed_at
                    """,
                    (
                        tape_id,
                        f["tape_path"],
                        namespace_prefix,
                        f["size_bytes"],
                        f["checksum_sha256"],
                        now,
                    ),
                )
            connection.execute(
                "UPDATE tapes SET last_indexed_at = ? WHERE id = ?",
                (now, tape_id),
            )


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _try_rmdir(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass


def cleanup_staged_job_cache(
    config: dict[str, Any],
    job: dict[str, Any],
) -> dict[str, Any]:
    source = job.get("source") or {}
    staging_dir = Path(source.get("staging_dir", ""))
    removed_bytes = 0
    removed_files = 0

    for staged_file in source.get("write_units") or source.get("files", []):
        staging_path = Path(staged_file.get("staging_path", ""))
        if staging_path.is_file():
            removed_bytes += staging_path.stat().st_size
            removed_files += 1

    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)

    with closing(db.connect(config)) as connection:
        with connection:
            connection.execute(
                """
                UPDATE cache_entries
                SET state = 'consumed'
                WHERE job_id = ? AND state = 'staged'
                """,
                (job["id"],),
            )

    return {
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "staging_dir": str(staging_dir),
    }


def _upsert_bundle_preview_catalog(
    config: dict[str, Any],
    tape_barcode: str,
    bundle_path: str,
    members: list[dict[str, Any]],
) -> None:
    if members == []:
        return
    indexed_at = _utc_now()
    with closing(db.connect(config)) as connection:
        with connection:
            tape_id = db.get_or_create_tape(connection, tape_barcode)
            db.upsert_bundle_members_with_connection(
                connection,
                tape_id,
                bundle_path,
                members,
                indexed_at=indexed_at,
            )


def cleanup_cache(config: dict[str, Any]) -> dict[str, Any]:
    db.initialize_database(config)
    cache_root = _cache_root(config)
    staging_root = cache_root / "staging" / "archive-jobs"
    temp_root = cache_root / "temp"
    removed_dirs: list[str] = []
    removed_files = 0
    removed_bytes = 0
    marked_missing_entries = 0

    jobs_by_id = {job["id"]: job for job in db.list_jobs(config, limit=5000)}

    with closing(db.connect(config)) as connection:
        rows = connection.execute(
            "SELECT id, job_id, cache_path, state FROM cache_entries ORDER BY id"
        ).fetchall()
        with connection:
            for row in rows:
                cache_path = Path(row["cache_path"] or "")
                job = jobs_by_id.get(row["job_id"])
                if not cache_path.exists() and row["state"] == "staged":
                    connection.execute(
                        "UPDATE cache_entries SET state = 'missing' WHERE id = ?",
                        (row["id"],),
                    )
                    marked_missing_entries += 1
                    continue
                if (
                    job is not None
                    and job["state"] in {"complete", "cancelled"}
                    and cache_path.is_file()
                ):
                    removed_bytes += cache_path.stat().st_size
                    removed_files += 1
                    cache_path.unlink(missing_ok=True)
                    connection.execute(
                        "UPDATE cache_entries SET state = 'consumed' WHERE id = ?",
                        (row["id"],),
                    )

    if staging_root.exists():
        for job_dir in sorted(staging_root.glob("*")):
            if not job_dir.is_dir():
                continue
            job = jobs_by_id.get(job_dir.name)
            if job is None:
                continue
            if job["state"] not in {"complete", "cancelled"}:
                continue
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)
                removed_dirs.append(str(job_dir))

    if temp_root.exists():
        for temp_file in sorted(temp_root.rglob("*")):
            if not temp_file.is_file():
                continue
            removed_bytes += temp_file.stat().st_size
            removed_files += 1
            temp_file.unlink(missing_ok=True)

    return {
        "generated_at": _utc_now(),
        "cache_root": str(cache_root),
        "removed_files": removed_files,
        "removed_bytes": removed_bytes,
        "removed_dirs": removed_dirs,
        "marked_missing_entries": marked_missing_entries,
        "available_bytes": _available_cache_bytes(config),
    }
