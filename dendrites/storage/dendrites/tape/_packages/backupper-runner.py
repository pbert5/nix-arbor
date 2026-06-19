#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import closing
import json
import re
import shutil
import subprocess
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from tapelib import archive, cli as tapelib_cli, db, executor, hardware
from tapelib.executor import ExecutionError


RUNNABLE_STATES = {"queued", "waiting_for_mount"}
RESUMABLE_STATES = RUNNABLE_STATES | {"failed", "needs_operator"}


class BackupperError(RuntimeError):
    pass


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _state_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("stateDir", "/var/lib/backupper"))


def _status_dir(config: dict[str, Any]) -> Path:
    return _state_dir(config) / "status"


def _refresh_inventory(config: dict[str, Any]) -> dict[str, Any]:
    inventory = hardware.read_changer_inventory(
        config.get("library", {}).get("changerDevice")
    ).as_dict()
    if inventory.get("error") is not None:
        raise BackupperError(str(inventory["error"]))
    db.apply_changer_inventory(config, inventory)
    return inventory


def _drive_configs(config: dict[str, Any]) -> list[dict[str, Any]]:
    return list(config.get("library", {}).get("drives", []))


def _drive_config(config: dict[str, Any], drive_name: str) -> tuple[int, dict[str, Any]]:
    for index, drive in enumerate(_drive_configs(config)):
        if drive["name"] == drive_name:
            return index, drive
    raise BackupperError(f"Unknown configured drive: {drive_name}")


def _drive_status(inventory: dict[str, Any], drive_index: int) -> dict[str, Any] | None:
    for drive in inventory.get("drives", []):
        if int(drive["index"]) == drive_index:
            return drive
    return None


def _selected_tape_barcodes(config: dict[str, Any]) -> set[str]:
    selected: set[str] = set()
    for entry in config.get("games", {}).get("selectedTapes", []):
        if isinstance(entry, str) and entry.strip():
            selected.add(entry.strip())
            continue
        if isinstance(entry, dict):
            barcode = entry.get("barcode")
            if isinstance(barcode, str) and barcode.strip():
                selected.add(barcode.strip())
    return selected


def _is_mounted(path: str) -> bool:
    result = subprocess.run(
        ["findmnt", "-n", "--output", "TARGET", "--target", path],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False
    return result.stdout.strip() == path


def _maybe_unmount_drive(config: dict[str, Any], drive_name: str, mount_path: str) -> None:
    if not _is_mounted(mount_path):
        return
    try:
        executor.unmount_ltfs(config, drive_name)
    except Exception as exc:  # pragma: no cover - best effort cleanup
        raise BackupperError(
            f"Failed to unmount LTFS on {drive_name} at {mount_path}: {exc}"
        ) from exc


def _reset_unmounted_mount_path(mount_path: str) -> None:
    if _is_mounted(mount_path):
        return
    mount_root = Path(mount_path)
    mount_root.mkdir(parents=True, exist_ok=True)
    for child in mount_root.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def _run(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return
    message = completed.stderr.strip() or completed.stdout.strip()
    raise BackupperError(message or f"Command failed: {' '.join(command)}")


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


def _sg_device_for_drive(config: dict[str, Any], drive_name: str) -> str:
    _drive_index, drive = _drive_config(config, drive_name)
    sg_device = drive.get("sgDevice") or hardware.sg_device_for_st_device(drive["stDevice"])
    if not sg_device:
        raise BackupperError(f"No SCSI generic device could be resolved for {drive_name}.")
    return sg_device


def _auto_initialize_ltfs_media(
    config: dict[str, Any],
    drive_name: str,
    target_barcode: str,
) -> None:
    if not bool(config.get("archive", {}).get("autoInitializeLtfs", True)):
        raise BackupperError(
            f"Tape {target_barcode} is not LTFS-formatted and autoInitializeLtfs is disabled."
        )
    sg_device = _sg_device_for_drive(config, drive_name)
    _run(["mkltfs", "-d", sg_device, "-n", target_barcode])


def _configured_drive_name(config: dict[str, Any], drive_index: int) -> str:
    drives = _drive_configs(config)
    if drive_index >= len(drives):
        return f"drive{drive_index}"
    return drives[drive_index]["name"]


def _coverage_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("coverage", {}))


def _normalize_member_name(name: str) -> str:
    return re.sub(r"\s+", " ", Path(name).name.strip()).casefold()


def _normalize_member_path(name: str) -> str:
    normalized_parts = [
        re.sub(r"\s+", " ", part.strip()).casefold()
        for part in Path(name).parts
        if part not in ("", ".")
    ]
    return "/".join(normalized_parts)


def _audit_archive_coverage(config: dict[str, Any]) -> dict[str, Any]:
    coverage = _coverage_config(config)
    archive_roots = [Path(root) for root in coverage.get("archiveRoots", [])]
    loose_roots = [Path(root) for root in coverage.get("looseRoots", [])]
    zip_extensions = {
        str(ext).casefold()
        for ext in coverage.get("zipExtensions", [".zip"])
    }

    archive_members_by_path: dict[str, set[int]] = {}
    archive_members_by_name: dict[str, set[int]] = {}
    archive_file_count = 0
    archive_member_count = 0
    unreadable_archives: list[dict[str, str]] = []

    for root in archive_roots:
        if not root.exists():
            continue
        for archive_path in sorted(path for path in root.rglob("*") if path.is_file()):
            if archive_path.suffix.casefold() not in zip_extensions:
                continue
            archive_file_count += 1
            try:
                with zipfile.ZipFile(archive_path) as handle:
                    for member in handle.infolist():
                        if member.is_dir():
                            continue
                        archive_member_count += 1
                        member_size = int(member.file_size)
                        normalized_path = _normalize_member_path(member.filename)
                        normalized_name = _normalize_member_name(member.filename)
                        archive_members_by_path.setdefault(normalized_path, set()).add(member_size)
                        archive_members_by_name.setdefault(normalized_name, set()).add(member_size)
            except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
                unreadable_archives.append(
                    {
                        "archive_path": str(archive_path),
                        "error": str(exc),
                    }
                )

    represented_exact_files = 0
    represented_exact_bytes = 0
    represented_basename_files = 0
    represented_basename_bytes = 0
    represented_files = 0
    represented_bytes = 0
    missing_files = 0
    missing_bytes = 0
    missing_samples: list[dict[str, Any]] = []

    for root in loose_roots:
        if not root.exists():
            continue
        for loose_path in sorted(path for path in root.rglob("*") if path.is_file()):
            normalized_relative_path = _normalize_member_path(str(loose_path.relative_to(root)))
            normalized_name = _normalize_member_name(loose_path.name)
            size_bytes = loose_path.stat().st_size
            if size_bytes in archive_members_by_path.get(normalized_relative_path, set()):
                represented_exact_files += 1
                represented_exact_bytes += size_bytes
                represented_files += 1
                represented_bytes += size_bytes
                continue
            if size_bytes in archive_members_by_name.get(normalized_name, set()):
                represented_basename_files += 1
                represented_basename_bytes += size_bytes
                represented_files += 1
                represented_bytes += size_bytes
                continue

            missing_files += 1
            missing_bytes += size_bytes
            if len(missing_samples) < 100:
                missing_samples.append(
                    {
                        "path": str(loose_path),
                        "size_bytes": size_bytes,
                    }
                )

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "archive_file_count": archive_file_count,
        "archive_member_count": archive_member_count,
        "archive_unique_member_path_count": len(archive_members_by_path),
        "archive_unique_member_name_count": len(archive_members_by_name),
        "archive_roots": [str(root) for root in archive_roots],
        "loose_roots": [str(root) for root in loose_roots],
        "matching_strategy": [
            "exact-relative-path-plus-size",
            "basename-plus-size-fallback",
        ],
        "represented_basename_fallback_bytes": represented_basename_bytes,
        "represented_basename_fallback_files": represented_basename_files,
        "represented_exact_bytes": represented_exact_bytes,
        "represented_exact_files": represented_exact_files,
        "represented_files": represented_files,
        "represented_bytes": represented_bytes,
        "missing_files": missing_files,
        "missing_bytes": missing_bytes,
        "missing_samples": missing_samples,
        "unreadable_archives": unreadable_archives[:100],
        "unreadable_archive_count": len(unreadable_archives),
        "zip_extensions": sorted(zip_extensions),
    }
    _write_json(_status_dir(config) / "archive-coverage.json", report)

    max_missing_bytes = _parse_size_string(coverage.get("maxMissingBytes"))
    fail_on_missing = bool(coverage.get("failOnMissing", False))
    if fail_on_missing and missing_bytes > max_missing_bytes:
        raise BackupperError(
            "Archive coverage audit found loose files that are not represented inside "
            f"zip archives: {missing_files} files, {missing_bytes} bytes. "
            f"See {_status_dir(config) / 'archive-coverage.json'}."
        )

    if missing_bytes > max_missing_bytes > 0:
        print(
            "WARNING: archive coverage audit found loose files that are not represented "
            f"inside zip archives: {missing_files} files, {missing_bytes} bytes. "
            f"See {_status_dir(config) / 'archive-coverage.json'}.",
            flush=True,
        )

    return report


def _ensure_drive_ready(
    config: dict[str, Any],
    drive_name: str,
    target_barcode: str,
) -> str:
    drive_index, drive = _drive_config(config, drive_name)
    mount_path = drive["mountPath"]
    inventory = _refresh_inventory(config)

    loaded_elsewhere = None
    for status in inventory.get("drives", []):
        barcode = status.get("barcode")
        if barcode != target_barcode or int(status["index"]) == drive_index:
            continue
        loaded_elsewhere = _configured_drive_name(config, int(status["index"]))
        break

    if loaded_elsewhere is not None:
        other_mount = _drive_config(config, loaded_elsewhere)[1]["mountPath"]
        _maybe_unmount_drive(config, loaded_elsewhere, other_mount)
        executor.unload_tape(config, loaded_elsewhere)
        inventory = _refresh_inventory(config)

    drive_status = _drive_status(inventory, drive_index)
    current_barcode = None if drive_status is None else drive_status.get("barcode")

    if current_barcode and current_barcode != target_barcode:
        _maybe_unmount_drive(config, drive_name, mount_path)
        executor.unload_tape(config, drive_name)
        inventory = _refresh_inventory(config)
        drive_status = _drive_status(inventory, drive_index)
        current_barcode = None if drive_status is None else drive_status.get("barcode")

    if current_barcode != target_barcode:
        executor.load_tape(config, target_barcode, drive_name)

    if _is_mounted(mount_path) and not archive._is_mounted_rw(mount_path):
        _maybe_unmount_drive(config, drive_name, mount_path)

    if not archive._is_mounted_rw(mount_path):
        _reset_unmounted_mount_path(mount_path)
        try:
            executor.mount_ltfs(config, drive_name, read_only=False)
        except ExecutionError as exc:
            message = str(exc).lower()
            if "not partitioned" not in message:
                raise
            _auto_initialize_ltfs_media(config, drive_name, target_barcode)
            executor.mount_ltfs(config, drive_name, read_only=False)

    return mount_path


def _list_write_jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    selected_tapes = _selected_tape_barcodes(config)
    jobs = [
        job
        for job in db.list_jobs(config, limit=10000)
        if job["type"] == "write_archive"
        and (
            not selected_tapes
            or ((job.get("target") or {}).get("tape_barcode") in selected_tapes)
        )
    ]
    return sorted(jobs, key=lambda job: job.get("created_at") or "")


def _set_job_needs_operator(
    config: dict[str, Any],
    job_id: str,
    *,
    message: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job_id,
                "needs_operator",
                event_type="backupper_needs_operator",
                message=message,
                data=data,
                last_error=message,
            )
        return db.get_job(connection, job_id)


def _best_effort_drive_reset(config: dict[str, Any], drive_name: str) -> None:
    try:
        _refresh_inventory(config)
    except Exception:
        return

    _drive_index, drive = _drive_config(config, drive_name)
    mount_path = drive["mountPath"]
    try:
        if archive._is_mounted_rw(mount_path) or _is_mounted(mount_path):
            executor.unmount_ltfs(config, drive_name)
    except Exception:
        pass

    try:
        inventory = _refresh_inventory(config)
    except Exception:
        return
    drive_status = _drive_status(inventory, _drive_index)
    if drive_status is None or drive_status.get("state") != "full":
        return
    try:
        executor.unload_tape(config, drive_name)
    except Exception:
        pass


def _next_job_for_drive(
    config: dict[str, Any],
    drive_name: str,
    *,
    resume: bool,
) -> dict[str, Any] | None:
    runnable_states = RESUMABLE_STATES if resume else RUNNABLE_STATES
    drive_count = len(_drive_configs(config))

    for job in _list_write_jobs(config):
        assigned_drive = job.get("assigned_drive")
        if assigned_drive not in (None, "", drive_name):
            continue
        if assigned_drive in (None, "") and drive_count > 1:
            continue
        if job.get("state") in runnable_states:
            return job
    return None


def _plan_and_queue(config: dict[str, Any]) -> dict[str, Any]:
    plan = tapelib_cli._plan_game_backup(config)
    new_jobs = archive.stage_games_archive(config, plan)
    active_jobs = [
        job
        for job in _list_write_jobs(config)
        if job.get("state") in RUNNABLE_STATES
    ]
    payload = {
        "generated_at": plan["generated_at"],
        "active_job_count": len(active_jobs),
        "job_count": len(new_jobs),
        "new_job_count": len(new_jobs),
        "plan_tapes": len(plan.get("tapes", [])),
        "plan_units": plan.get("unit_count", 0),
    }
    _write_json(_status_dir(config) / "latest-plan.json", plan)
    _write_json(_status_dir(config) / "queue-summary.json", payload)
    return payload


def _worker(config_path: str, drive_name: str, *, resume: bool) -> dict[str, Any]:
    config = _load_config(Path(config_path))
    completed_jobs = 0
    needs_operator_jobs = 0
    touched_drive = False
    while True:
        _refresh_inventory(config)
        job = _next_job_for_drive(config, drive_name, resume=resume)
        if job is None:
            break

        tape_barcode = (job.get("target") or {}).get("tape_barcode")
        if not isinstance(tape_barcode, str) or not tape_barcode:
            raise BackupperError(f"Job {job['id']} is missing target.tape_barcode")

        try:
            mount_path = _ensure_drive_ready(config, drive_name, tape_barcode)
            touched_drive = True
            if bool(config.get("archive", {}).get("catalogLoadedTapeBeforeWrite", True)):
                db.index_tape(config, tape_barcode, mount_path)

            refreshed_job = db.get_job_by_id(config, job["id"])
            archive.write_staged_archive(config, refreshed_job, resume=resume)
            completed_jobs += 1
        except Exception as exc:
            message = (
                f"Hardware preparation or LTFS mount failed for tape {tape_barcode} "
                f"on {drive_name}. The job was quarantined for operator review: {exc}"
            )
            _set_job_needs_operator(
                config,
                job["id"],
                message=message,
                data={
                    "drive": drive_name,
                    "tape_barcode": tape_barcode,
                },
            )
            _best_effort_drive_reset(config, drive_name)
            needs_operator_jobs += 1
            continue

    if touched_drive:
        _refresh_inventory(config)
        _drive_index, drive = _drive_config(config, drive_name)
        mount_path = drive["mountPath"]
        if archive._is_mounted_rw(mount_path) or _is_mounted(mount_path):
            executor.unmount_ltfs(config, drive_name)
        inventory = _refresh_inventory(config)
        drive_status = _drive_status(inventory, _drive_index)
        if drive_status is not None and drive_status.get("state") == "full":
            executor.unload_tape(config, drive_name)

    return {
        "drive": drive_name,
        "completed_jobs": completed_jobs,
        "needs_operator_jobs": needs_operator_jobs,
    }


def run(config_path: Path, *, resume: bool) -> dict[str, Any]:
    config = _load_config(config_path)
    db.initialize_database(config)
    interrupted_jobs = db.reconcile_interrupted_jobs(config)
    _refresh_inventory(config)
    coverage_report = _audit_archive_coverage(config)
    queue_summary = _plan_and_queue(config)

    drive_names = [drive["name"] for drive in _drive_configs(config)]
    with ThreadPoolExecutor(max_workers=max(1, len(drive_names))) as pool:
        futures = [
            pool.submit(_worker, str(config_path), drive_name, resume=resume)
            for drive_name in drive_names
        ]
        worker_results = [future.result() for future in futures]

    result = {
        "config": str(config_path),
        "coverage_report": {
            "missing_bytes": coverage_report["missing_bytes"],
            "missing_files": coverage_report["missing_files"],
            "represented_basename_fallback_files": coverage_report["represented_basename_fallback_files"],
            "represented_exact_files": coverage_report["represented_exact_files"],
            "represented_bytes": coverage_report["represented_bytes"],
            "represented_files": coverage_report["represented_files"],
            "unreadable_archive_count": coverage_report["unreadable_archive_count"],
        },
        "interrupted_jobs_reconciled": len(interrupted_jobs),
        "queue_summary": queue_summary,
        "workers": worker_results,
    }
    _write_json(_status_dir(config) / "last-run.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a declarative LTFS backupper plan.")
    parser.add_argument("--config", required=True, help="Path to a backupper plan JSON file.")
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Do not resume failed write jobs; only queued and waiting jobs are runnable.",
    )
    args = parser.parse_args()
    result = run(Path(args.config), resume=not args.no_resume)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
