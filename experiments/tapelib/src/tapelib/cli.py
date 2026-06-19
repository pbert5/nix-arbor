from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import shutil
import signal
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import db
from . import executor
from . import hardware
from . import job_status

RETRIEVE_JOB_TYPE = "retrieve_files"
RETRIEVE_QUEUE_STATES = [
    "created",
    "queued",
    "waiting_for_cache",
    "waiting_for_mount",
]
CANCELLABLE_JOB_STATES = set(RETRIEVE_QUEUE_STATES)
RUNNABLE_RETRIEVE_STATES = ["queued", "waiting_for_mount"]
AUTO_RETRIEVE_STATES = [
    "queued",
    "waiting_for_drive",
    "waiting_for_changer",
    "waiting_for_mount",
]
WRITE_ARCHIVE_JOB_TYPE = "write_archive"
FILESYSTEM_FAST_BUDGET_MS = 250.0
FILESYSTEM_HARDWARE_BUDGET_MS = 5000.0


def _default_config_path() -> Path:
    return Path(os.environ.get("TAPELIB_CONFIG_PATH", "/etc/tapelib/config.json"))


def _parse_size_string(s: str) -> int:
    """Parse a size string like '50G', '900G', '1T' into bytes."""
    s = str(s).strip()
    suffixes = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    if s[-1].upper() in suffixes:
        return int(float(s[:-1]) * suffixes[s[-1].upper()])
    return int(s)


def _format_int(value: int) -> str:
    return f"{value:,}"


def _format_gib(value: int, *, digits: int = 2) -> str:
    return f"{value / (1024**3):,.{digits}f} GiB"


def _load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _state_dir(config: dict[str, Any]) -> Path:
    return Path(config.get("stateDir", "/var/lib/tapelib"))


def _status_path(config: dict[str, Any]) -> Path:
    return _state_dir(config) / "status" / "status.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    try:
        path.chmod(0o660)
    except PermissionError:
        pass


def _checksum_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_arg(value: str | None) -> Any:
    if value in (None, ""):
        return None
    return json.loads(value)


def _readable_inventory(config: dict[str, Any]) -> dict[str, Any]:
    library = config.get("library", {})
    drives = library.get("drives", [])
    return {
        "changer_device": library.get("changerDevice"),
        "drive_count": len(drives),
        "drives": drives,
    }


def _inventory_payload(config: dict[str, Any]) -> dict[str, Any]:
    changer_inventory = hardware.read_changer_inventory(
        config.get("library", {}).get("changerDevice")
    ).as_dict()
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "configured": _readable_inventory(config),
        "inventory": changer_inventory,
        "cache": config.get("cache", {}),
        "database": config.get("database", {}),
        "fuse": config.get("fuse", {}),
        "games": {
            "sourceRoots": config.get("games", {}).get("sourceRoots", []),
            "selectedTapes": config.get("games", {}).get("selectedTapes", []),
        },
    }
    return payload


def _command_inventory(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    database = db.initialize_database(config)
    payload = _inventory_payload(config)
    if payload["inventory"].get("error") is None:
        database = db.apply_changer_inventory(config, payload["inventory"])
    payload["database"] = database
    if args.write_status:
        _write_json(_state_dir(config) / "status" / "inventory.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _status_payload(config: dict[str, Any]) -> dict[str, Any]:
    status_file = _status_path(config)
    runtime_status: dict[str, Any] = {}
    if status_file.exists():
        runtime_status = json.loads(status_file.read_text(encoding="utf-8"))
    database = db.initialize_database(config)
    return {
        "config": {
            "database": config.get("database", {}),
            "webui": config.get("webui", {}),
            "stateDir": config.get("stateDir"),
        },
        "database": database,
        "jobs": db.list_jobs(config, limit=20),
        "runtime": runtime_status,
    }


def _cache_payload(config: dict[str, Any]) -> dict[str, Any]:
    cache_path = Path(
        config.get("cache", {}).get("path", "/run/media/ash/cache/tapelib")
    )
    cache_exists = False
    cache_error = None
    try:
        cache_exists = cache_path.exists()
    except OSError as exc:
        cache_error = str(exc)

    payload: dict[str, Any] = {
        "path": str(cache_path),
        "configured": config.get("cache", {}),
        "exists": cache_exists,
        "entries_by_state": {},
    }
    if cache_error:
        payload["error"] = cache_error
    if cache_exists:
        try:
            statvfs = os.statvfs(cache_path)
            payload.update(
                {
                    "free_bytes": statvfs.f_frsize * statvfs.f_bavail,
                    "total_bytes": statvfs.f_frsize * statvfs.f_blocks,
                }
            )
        except OSError as exc:
            payload["error"] = str(exc)

    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        rows = connection.execute(
            """
            SELECT state, COUNT(*) AS count, COALESCE(SUM(size_bytes), 0) AS size_bytes
            FROM cache_entries
            GROUP BY state
            ORDER BY state
            """
        ).fetchall()
    payload["entries_by_state"] = {
        row["state"] or "unknown": {
            "count": row["count"],
            "size_bytes": row["size_bytes"],
        }
        for row in rows
    }
    return payload


def _read_status_json(config: dict[str, Any], name: str) -> dict[str, Any] | None:
    path = _state_dir(config) / "status" / name
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _warnings_payload(config: dict[str, Any]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    for job in db.list_jobs(config, limit=200):
        if job["state"] in {"failed", "needs_operator"}:
            warnings.append(
                {
                    "kind": "job",
                    "severity": "error" if job["state"] == "failed" else "warning",
                    "job_id": job["id"],
                    "job_type": job["type"],
                    "state": job["state"],
                    "message": job.get("last_error") or f"Job is {job['state']}.",
                }
            )
        elif job["type"] == "write_archive" and job["state"] in {
            "queued",
            "waiting_for_mount",
        }:
            warnings.append(
                {
                    "kind": "job",
                    "severity": "info",
                    "job_id": job["id"],
                    "job_type": job["type"],
                    "state": job["state"],
                    "message": "Archive write is queued and waiting for its target tape.",
                }
            )

    for file_row in db.list_files(config):
        if file_row.get("state") in {"read_error", "missing_after_reindex"}:
            warnings.append(
                {
                    "kind": "file",
                    "severity": "error",
                    "tape_barcode": file_row["tape_barcode"],
                    "path": file_row["path"],
                    "state": file_row["state"],
                    "message": "Cataloged file needs operator attention.",
                }
            )

    verify = _read_status_json(config, "verify.json")
    if verify is not None:
        missing = int(verify.get("missing_files") or 0)
        mismatches = int(verify.get("checksum_mismatches") or 0)
        if missing or mismatches:
            warnings.append(
                {
                    "kind": "verify",
                    "severity": "error",
                    "missing_files": missing,
                    "checksum_mismatches": mismatches,
                    "message": "Latest verification found missing files or checksum mismatches.",
                }
            )

    cache = _cache_payload(config)
    if not cache.get("exists"):
        message = "Cache path does not exist."
        if cache.get("error"):
            message = f"Cache path is not readable: {cache['error']}"
        warnings.append(
            {
                "kind": "cache",
                "severity": "warning",
                "message": message,
                "path": cache["path"],
            }
        )
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "warnings": warnings,
        "warning_count": len(warnings),
    }


def _files_payload(
    config: dict[str, Any],
    *,
    tape_barcode: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    files = db.list_files(config, tape_barcode=tape_barcode)
    return {
        "files": files[:limit],
        "limit": limit,
        "returned": min(len(files), limit),
        "total": len(files),
        "tape_barcode": tape_barcode,
    }


def _console_job_payload(job: dict[str, Any]) -> dict[str, Any]:
    compact = dict(job)
    source = compact.get("source")
    if isinstance(source, dict) and isinstance(source.get("files"), list):
        source = dict(source)
        source["file_count"] = len(source.pop("files"))
        compact["source"] = source
    return compact


def _console_status_payload(config: dict[str, Any]) -> dict[str, Any]:
    payload = _status_payload(config)
    payload["jobs"] = [
        _console_job_payload(job) for job in payload.get("jobs", [])
    ]
    return payload


def _operator_console_payload(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "cache": _cache_payload(config),
        "drives": db.list_drives(config),
        "jobs": [
            _console_job_payload(job) for job in db.list_jobs(config, limit=50)
        ],
        "status": _console_status_payload(config),
        "tapes": db.list_tapes(config, include_ignored=True),
        "warnings": _warnings_payload(config),
    }


def _web_confirm(action: str, payload: dict[str, Any]) -> None:
    if payload.get("confirm") != action:
        raise executor.ExecutionError(f"{action} action requires confirm='{action}'.")


def _web_required_string(
    action: str, payload: dict[str, Any], *names: str
) -> str:
    for name in names:
        value = payload.get(name)
        if isinstance(value, str) and value.strip() != "":
            return value.strip()
    label = " or ".join(names)
    raise executor.ExecutionError(f"{action} action requires {label}.")


def _web_optional_int(payload: dict[str, Any], *names: str) -> int | None:
    for name in names:
        value = payload.get(name)
        if value is None or value == "":
            continue
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise executor.ExecutionError(f"{name} must be an integer.") from exc
    return None


def _web_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _web_action(
    config: dict[str, Any], action: str, payload: dict[str, Any]
) -> dict[str, Any]:
    if action == "inventory":
        inventory = _inventory_payload(config)
        database = None
        if inventory["inventory"].get("error") is None:
            database = db.apply_changer_inventory(config, inventory["inventory"])
        return {"action": action, "inventory": inventory, "database": database}

    if action == "retrieve":
        manifest = payload.get("manifest")
        if manifest is None:
            manifest = {"files": payload.get("files", [])}
        dest = payload.get("dest") or payload.get("destination_root")
        if not isinstance(dest, str) or dest.strip() == "":
            raise executor.ExecutionError("retrieve action requires dest.")
        plan = _build_retrieve_plan_from_manifest(
            config,
            manifest,
            manifest_path="web-action",
            destination_root=Path(dest),
        )
        result = _queue_retrieve_plan(
            config,
            plan,
            priority=int(payload.get("priority", 100)),
        )
        return {"action": action, **result}

    if action == "cancel":
        _web_confirm(action, payload)
        job_id = payload.get("job_id")
        if not isinstance(job_id, str) or job_id == "":
            raise executor.ExecutionError("cancel action requires job_id.")
        job = db.get_job_by_id(config, job_id)
        if job["state"] not in CANCELLABLE_JOB_STATES:
            raise executor.ExecutionError(
                f"Job {job_id} is {job['state']} and cannot be cancelled safely."
            )
        with closing(db.connect(config)) as connection:
            with connection:
                db.transition_job(
                    connection,
                    job_id,
                    "cancelled",
                    event_type="job_cancelled",
                    message="Queued job cancelled through the web action API.",
                    data={"previous_state": job["state"]},
                )
                return {"action": action, "job": db.get_job(connection, job_id)}

    if action == "promote-ingest":
        _web_confirm(action, payload)
        from . import archive as _archive

        job_id = payload.get("job_id")
        tape = payload.get("tape")
        if not isinstance(job_id, str) or job_id == "":
            raise executor.ExecutionError("promote-ingest action requires job_id.")
        if not isinstance(tape, str) or tape == "":
            raise executor.ExecutionError("promote-ingest action requires tape.")
        job = db.get_job_by_id(config, job_id)
        result = _archive.promote_cached_ingest(
            config,
            job,
            tape_barcode=tape,
            namespace_prefix=payload.get("namespace"),
        )
        return {"action": action, **result}

    if action == "verify":
        _web_confirm(action, payload)
        mode = payload.get("mode", "metadata")
        if mode not in {"metadata", "checksums"}:
            raise executor.ExecutionError("verify mode must be metadata or checksums.")
        target = payload.get("target", payload.get("tape"))
        if target is not None and not isinstance(target, str):
            raise executor.ExecutionError("verify target must be a string.")
        return {
            "action": action,
            "verification": _verify_payload(config, target=target, mode=mode),
        }

    if action == "index-tape":
        _web_confirm(action, payload)
        target = _web_required_string(action, payload, "target", "tape", "drive")
        barcode, mount_path, drive = _resolve_tape_target(
            config, target, require_mounted=True
        )
        result = db.index_tape(config, barcode, mount_path)
        return {
            "action": action,
            "tape_barcode": barcode,
            "drive": drive,
            "mount_path": mount_path,
            "index": result,
        }

    if action == "load-tape":
        _web_confirm(action, payload)
        barcode = _web_required_string(action, payload, "barcode", "tape")
        drive = _web_required_string(action, payload, "drive")
        return {
            "action": action,
            "job": executor.load_tape(config, barcode, drive),
        }

    if action == "unload-tape":
        _web_confirm(action, payload)
        drive = _web_required_string(action, payload, "drive")
        return {
            "action": action,
            "job": executor.unload_tape(
                config,
                drive,
                destination_slot=_web_optional_int(payload, "slot", "destination_slot"),
            ),
        }

    if action == "mount-ltfs":
        _web_confirm(action, payload)
        drive = _web_required_string(action, payload, "drive")
        read_only = _web_bool(payload.get("read_only", True))
        if "read_write" in payload:
            read_only = not _web_bool(payload["read_write"])
        return {
            "action": action,
            "job": executor.mount_ltfs(config, drive, read_only=read_only),
        }

    if action == "unmount-ltfs":
        _web_confirm(action, payload)
        drive = _web_required_string(action, payload, "drive")
        return {
            "action": action,
            "job": executor.unmount_ltfs(config, drive),
        }

    raise executor.ExecutionError(f"Unknown web action: {action}")


def _command_status(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    print(json.dumps(_status_payload(config), indent=2, sort_keys=True))
    return 0


def _time_filesystem_operation(
    *,
    label: str,
    path: Path,
    operation: str,
    category: str,
    budget_ms: float,
    action: Callable[[], Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    error = None
    sample = None
    try:
        value = action()
        if isinstance(value, list):
            sample = value[:10]
        elif isinstance(value, (str, int)):
            sample = value
    except OSError as exc:
        error = str(exc)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "label": label,
        "path": str(path),
        "operation": operation,
        "category": category,
        "budget_ms": budget_ms,
        "elapsed_ms": elapsed_ms,
        "ok": error is None and elapsed_ms <= budget_ms,
        "error": error,
        "sample": sample,
    }


def _list_names(path: Path) -> list[str]:
    return sorted(os.listdir(path))


def _stat_mode_size(path: Path) -> str:
    st = path.stat()
    return f"{st.st_mode:o}:{st.st_size}"


def _read_prefix(path: Path, size: int = 4096) -> int:
    with path.open("rb") as handle:
        return len(handle.read(size))


def _filesystem_smoke_payload(
    config: dict[str, Any],
    *,
    mount_point: Path | None = None,
    include_hardware: bool = False,
    fast_budget_ms: float = FILESYSTEM_FAST_BUDGET_MS,
) -> dict[str, Any]:
    root = mount_point or Path(
        config.get("fuse", {}).get("mountPoint", "/mnt/tapelib")
    )
    results: list[dict[str, Any]] = []

    def run(
        label: str,
        relative: str,
        operation: str,
        action: Callable[[], Any],
        *,
        category: str = "virtual-fast",
        budget_ms: float = fast_budget_ms,
    ) -> None:
        path = root / relative.lstrip("/")
        results.append(
            _time_filesystem_operation(
                label=label,
                path=path,
                operation=operation,
                category=category,
                budget_ms=budget_ms,
                action=action,
            )
        )

    run("root stat", ".", "stat", lambda: _stat_mode_size(root))
    run("root list", ".", "listdir", lambda: _list_names(root))
    run(
        "root README stat",
        "README.txt",
        "stat",
        lambda: _stat_mode_size(root / "README.txt"),
    )
    run(
        "root README read",
        "README.txt",
        "read",
        lambda: _read_prefix(root / "README.txt"),
    )

    for directory in [
        "browse",
        "readable",
        "jobs",
        "system",
        "thumbnails",
        "write",
    ]:
        run(
            f"{directory} stat",
            directory,
            "stat",
            lambda directory=directory: _stat_mode_size(root / directory),
        )
        run(
            f"{directory} list",
            directory,
            "listdir",
            lambda directory=directory: _list_names(root / directory),
        )

    tape_names: list[str] = []
    try:
        tape_names = _list_names(root / "browse")
    except OSError:
        tape_names = []
    if tape_names:
        tape = tape_names[0]
        for prefix in ["browse", "readable"]:
            run(
                f"{prefix} tape stat",
                f"{prefix}/{tape}",
                "stat",
                lambda prefix=prefix, tape=tape: _stat_mode_size(
                    root / prefix / tape
                ),
            )
            run(
                f"{prefix} tape list",
                f"{prefix}/{tape}",
                "listdir",
                lambda prefix=prefix, tape=tape: _list_names(root / prefix / tape),
            )
            run(
                f"{prefix} tape README read",
                f"{prefix}/{tape}/README.txt",
                "read",
                lambda prefix=prefix, tape=tape: _read_prefix(
                    root / prefix / tape / "README.txt"
                ),
            )

    for relative in [
        "system/config.json",
        "system/status.json",
        "system/inventory.json",
        "jobs/jobs.json",
        "jobs/journal.json",
        "thumbnails/README.txt",
        "thumbnails/cached/README.txt",
        "write/README.txt",
        "write/inbox-cached/README.txt",
        "write/inbox-direct/README.txt",
    ]:
        run(
            f"{relative} stat",
            relative,
            "stat",
            lambda relative=relative: _stat_mode_size(root / relative),
        )

    for relative in [
        "system/config.json",
        "system/status.json",
        "jobs/jobs.json",
        "jobs/journal.json",
        "thumbnails/README.txt",
        "write/README.txt",
    ]:
        run(
            f"{relative} read",
            relative,
            "read",
            lambda relative=relative: _read_prefix(root / relative),
        )

    run(
        "system drives list",
        "system/drives",
        "listdir",
        lambda: _list_names(root / "system/drives"),
    )
    try:
        drive_files = _list_names(root / "system/drives")
    except OSError:
        drive_files = []
    for drive_file in drive_files[:2]:
        run(
            f"system drive read {drive_file}",
            f"system/drives/{drive_file}",
            "read",
            lambda drive_file=drive_file: _read_prefix(
                root / "system" / "drives" / drive_file
            ),
        )

    if include_hardware:
        run(
            "system inventory read",
            "system/inventory.json",
            "read",
            lambda: _read_prefix(root / "system" / "inventory.json"),
            category="hardware-observation",
            budget_ms=FILESYSTEM_HARDWARE_BUDGET_MS,
        )

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mount_point": str(root),
        "include_hardware": include_hardware,
        "fast_budget_ms": fast_budget_ms,
        "results": results,
        "ok": all(result["ok"] for result in results),
        "slow": [result for result in results if not result["ok"]],
    }


def _render_filesystem_smoke(payload: dict[str, Any]) -> str:
    lines = [
        f"Tapelib filesystem smoke test: {'PASS' if payload['ok'] else 'SLOW/FAILED'}",
        f"Mount point: {payload['mount_point']}",
        f"Fast budget: {payload['fast_budget_ms']:.1f} ms",
        "",
    ]
    for result in payload["results"]:
        status = "OK" if result["ok"] else "SLOW"
        if result["error"] is not None:
            status = "ERR"
        lines.append(
            f"{status:<4} {result['elapsed_ms']:>8.1f} ms "
            f"{result['category']:<20} {result['operation']:<7} {result['path']}"
        )
        if result["error"] is not None:
            lines.append(f"     error: {result['error']}")
    return "\n".join(lines) + "\n"


def _command_filesystem_smoke_test(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    payload = _filesystem_smoke_payload(
        config,
        mount_point=Path(args.mount_point) if args.mount_point else None,
        include_hardware=args.include_hardware,
        fast_budget_ms=args.fast_budget_ms,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_filesystem_smoke(payload), end="")
    return 1 if args.fail_slow and not payload["ok"] else 0


def _command_init_db(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    print(json.dumps(db.initialize_database(config), indent=2, sort_keys=True))
    return 0


def _command_backup_db(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    payload = db.backup_database(config, destination_dir=args.output_dir)
    _write_json(_state_dir(config) / "status" / "database-backup.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _command_create_job(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    job = db.create_job(
        config,
        args.job_type,
        priority=args.priority,
        source=_json_arg(args.source_json),
        target=_json_arg(args.target_json),
        required_bytes=args.required_bytes,
        assigned_drive=args.assigned_drive,
        assigned_tape_id=args.assigned_tape_id,
    )
    print(json.dumps(job, indent=2, sort_keys=True))
    return 0


def _command_retrieve(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    plan = _build_retrieve_plan(config, Path(args.manifest), Path(args.dest))
    result = _queue_retrieve_plan(config, plan, priority=args.priority)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _build_retrieve_plan(
    config: dict[str, Any], manifest_path: Path, destination_root: Path
) -> dict[str, Any]:
    if not manifest_path.exists():
        raise executor.ExecutionError(f"Retrieve manifest not found: {manifest_path}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise executor.ExecutionError(
            f"Retrieve manifest is not valid JSON: {exc}"
        ) from exc

    return _build_retrieve_plan_from_manifest(
        config,
        manifest,
        manifest_path=str(manifest_path),
        destination_root=destination_root,
    )


def _build_retrieve_plan_from_manifest(
    config: dict[str, Any],
    manifest: Any,
    *,
    manifest_path: str,
    destination_root: Path,
) -> dict[str, Any]:
    entries = _retrieve_manifest_entries(manifest)
    if entries == []:
        raise executor.ExecutionError("Retrieve manifest must contain at least one file.")

    destination_root = destination_root.expanduser()
    requested_files: list[dict[str, Any]] = []
    seen_destinations: set[str] = set()
    total_bytes = 0

    for index, entry in enumerate(entries):
        tape_barcode, archive_path = _retrieve_entry_tape_path(entry)
        clean_path = _clean_archive_path(archive_path)
        catalog_file = db.get_file(
            config, tape_barcode=tape_barcode, path=clean_path
        )
        if catalog_file is None:
            raise executor.ExecutionError(
                f"Manifest entry {index + 1} does not match the catalog: {tape_barcode}:/{clean_path}"
            )

        destination_path = destination_root / tape_barcode / Path(clean_path)
        destination_key = str(destination_path)
        if destination_key in seen_destinations:
            raise executor.ExecutionError(
                f"Retrieve manifest maps more than one entry to {destination_key}."
            )
        seen_destinations.add(destination_key)

        size_bytes = int(catalog_file["size_bytes"] or 0)
        total_bytes += size_bytes
        requested_files.append(
            {
                "tape_barcode": tape_barcode,
                "archive_path": clean_path,
                "destination_path": destination_key,
                "size_bytes": size_bytes,
                "checksum_sha256": catalog_file.get("checksum_sha256"),
            }
        )

    requested_files.sort(
        key=lambda file: (file["tape_barcode"], file["archive_path"])
    )
    groups = _retrieve_groups(config, requested_files)
    return {
        "manifest_path": manifest_path,
        "destination_root": str(destination_root),
        "layout": "preserve_tape_and_archive_path",
        "total_bytes": total_bytes,
        "file_count": len(requested_files),
        "files": requested_files,
        "groups": groups,
    }


def _retrieve_manifest_entries(manifest: Any) -> list[Any]:
    if isinstance(manifest, list):
        return manifest
    if isinstance(manifest, dict) and isinstance(manifest.get("files"), list):
        return manifest["files"]
    raise executor.ExecutionError(
        "Retrieve manifest must be a JSON list, or an object with a 'files' list."
    )


def _retrieve_entry_tape_path(entry: Any) -> tuple[str, str]:
    if isinstance(entry, str):
        if ":" not in entry:
            raise executor.ExecutionError(
                f"Retrieve entry must be TAPE:/path, got: {entry}"
            )
        tape_barcode, archive_path = entry.split(":", 1)
    elif isinstance(entry, dict):
        tape_barcode = (
            entry.get("tape_barcode") or entry.get("tape") or entry.get("barcode")
        )
        archive_path = (
            entry.get("archive_path")
            or entry.get("archived_path")
            or entry.get("path")
        )
    else:
        raise executor.ExecutionError(
            f"Retrieve entry must be a string or object, got {type(entry).__name__}."
        )

    if not isinstance(tape_barcode, str) or tape_barcode.strip() == "":
        raise executor.ExecutionError("Retrieve entry is missing a tape barcode.")
    if not isinstance(archive_path, str) or archive_path.strip() == "":
        raise executor.ExecutionError("Retrieve entry is missing an archived path.")
    return tape_barcode.strip(), archive_path.strip()


def _clean_archive_path(path: str) -> str:
    cleaned = posixpath.normpath(str(PurePosixPath("/") / path.lstrip("/"))).lstrip("/")
    if cleaned in {"", "."} or cleaned == ".." or cleaned.startswith("../"):
        raise executor.ExecutionError(f"Unsafe archived path in retrieve manifest: {path}")
    return cleaned


def _retrieve_groups(
    config: dict[str, Any], requested_files: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for requested_file in requested_files:
        grouped.setdefault(requested_file["tape_barcode"], []).append(requested_file)

    tape_by_id = {
        tape["id"]: tape["barcode"]
        for tape in db.list_tapes(config, include_ignored=True)
        if tape.get("id") is not None
    }
    loaded_order = []
    for drive in db.list_drives(config):
        barcode = tape_by_id.get(drive.get("loaded_tape_id"))
        if barcode in grouped and barcode not in loaded_order:
            loaded_order.append(barcode)

    remaining_order = [
        tape_barcode
        for tape_barcode in grouped
        if tape_barcode not in set(loaded_order)
    ]
    ordered_tapes = loaded_order + remaining_order
    return [
        {
            "tape_barcode": tape_barcode,
            "file_count": len(grouped[tape_barcode]),
            "total_bytes": sum(file["size_bytes"] for file in grouped[tape_barcode]),
            "files": grouped[tape_barcode],
        }
        for tape_barcode in ordered_tapes
    ]


def _queue_retrieve_plan(
    config: dict[str, Any], plan: dict[str, Any], *, priority: int = 100
) -> dict[str, Any]:
    source = {
        "kind": "retrieve_manifest",
        "layout": plan["layout"],
        "files": plan["files"],
    }
    target = {
        "destination_root": plan["destination_root"],
        "groups": plan["groups"],
    }

    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        with connection:
            existing_job = db.find_matching_job(
                connection,
                RETRIEVE_JOB_TYPE,
                states=RETRIEVE_QUEUE_STATES,
                source=source,
                target=target,
            )
            if existing_job is not None:
                db.append_job_event(
                    connection,
                    existing_job["id"],
                    "retrieve_job_joined",
                    "Retrieve request joined an existing queued job.",
                    {"manifest_path": plan["manifest_path"]},
                )
                return {
                    "coalesced": True,
                    "job": db.get_job(connection, existing_job["id"]),
                    "plan": plan,
                }

            job = db.create_job_with_connection(
                connection,
                RETRIEVE_JOB_TYPE,
                state="queued",
                priority=priority,
                source=source,
                target=target,
                required_bytes=plan["total_bytes"],
            )
            db.append_job_event(
                connection,
                job["id"],
                "retrieve_job_queued",
                "Retrieve job queued for later tape-optimized copy-out.",
                {
                    "file_count": plan["file_count"],
                    "total_bytes": plan["total_bytes"],
                    "manifest_path": plan["manifest_path"],
                },
            )
            return {
                "coalesced": False,
                "job": db.get_job(connection, job["id"]),
                "plan": plan,
            }


def _command_cancel(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    try:
        job = db.get_job_by_id(config, args.job_id)
    except KeyError as exc:
        raise executor.ExecutionError(f"Unknown job id: {args.job_id}") from exc

    if job["state"] not in CANCELLABLE_JOB_STATES:
        raise executor.ExecutionError(
            f"Job {args.job_id} is {job['state']} and cannot be cancelled safely."
        )

    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                args.job_id,
                "cancelled",
                event_type="job_cancelled",
                message="Queued job cancelled before active hardware work.",
                data={"previous_state": job["state"]},
            )
            print(
                json.dumps(db.get_job(connection, args.job_id), indent=2, sort_keys=True)
            )
    return 0


def _command_run_queue(args: argparse.Namespace) -> int:
    if not args.once:
        raise executor.ExecutionError("run-queue currently requires --once.")
    config = _load_config(Path(args.config))
    result = _run_queue_once(config, job_id=args.job_id, auto=args.auto)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_queue_once(
    config: dict[str, Any],
    *,
    job_id: str | None = None,
    auto: bool = False,
) -> dict[str, Any]:
    try:
        job = _next_retrieve_job(
            config,
            job_id=job_id,
            states=AUTO_RETRIEVE_STATES if auto else RUNNABLE_RETRIEVE_STATES,
        )
    except KeyError as exc:
        raise executor.ExecutionError(f"Unknown job id: {job_id}") from exc
    if job is None:
        return {
            "ran": False,
            "job": None,
            "state": "idle",
            "message": "No runnable retrieve job is queued.",
            "copied_files": [],
            "blocked_tapes": [],
        }
    if job["type"] != RETRIEVE_JOB_TYPE:
        raise executor.ExecutionError(
            f"Job {job['id']} is {job['type']}, not {RETRIEVE_JOB_TYPE}."
        )
    runnable_states = AUTO_RETRIEVE_STATES if auto else RUNNABLE_RETRIEVE_STATES
    if job["state"] not in runnable_states:
        raise executor.ExecutionError(
            f"Job {job['id']} is {job['state']} and is not runnable by this queue mode."
        )
    if auto:
        return _run_automatic_retrieve_job(config, job)

    mount_map = _mounted_tape_map(config)
    required_tapes = _required_retrieve_tapes(job)
    blocked_tapes = [tape for tape in required_tapes if tape not in mount_map]
    if blocked_tapes:
        with closing(db.connect(config)) as connection:
            with connection:
                db.transition_job(
                    connection,
                    job["id"],
                    "waiting_for_mount",
                    event_type="retrieve_waiting_for_mount",
                    message="Retrieve job is waiting for all required tapes to be mounted.",
                    data={"blocked_tapes": blocked_tapes},
                )
                updated_job = db.get_job(connection, job["id"])
        return {
            "ran": False,
            "job": updated_job,
            "state": "waiting_for_mount",
            "message": "Required tapes are not mounted.",
            "copied_files": [],
            "blocked_tapes": blocked_tapes,
        }

    try:
        return _run_mounted_retrieve_job(config, job, mount_map)
    except executor.ExecutionError as exc:
        _fail_job_for_queue(config, job["id"], str(exc))
        failed_job = db.get_job_by_id(config, job["id"])
        return {
            "ran": True,
            "job": failed_job,
            "state": "failed",
            "message": str(exc),
            "copied_files": [],
            "blocked_tapes": [],
        }


def _next_retrieve_job(
    config: dict[str, Any],
    *,
    job_id: str | None = None,
    states: list[str] | None = None,
) -> dict[str, Any] | None:
    states = states or RUNNABLE_RETRIEVE_STATES
    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        if job_id is not None:
            return db.get_job(connection, job_id)
        placeholders = ", ".join("?" for _ in states)
        row = connection.execute(
            f"""
            SELECT * FROM jobs
            WHERE type = ?
              AND state IN ({placeholders})
            ORDER BY priority, created_at
            LIMIT 1
            """,
            (RETRIEVE_JOB_TYPE, *states),
        ).fetchone()
        return None if row is None else db.decode_job_row(row)


def _required_retrieve_tapes(job: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    tapes = []
    for group in (job.get("target") or {}).get("groups", []):
        tape = group.get("tape_barcode")
        if isinstance(tape, str) and tape not in seen:
            seen.add(tape)
            tapes.append(tape)
    return tapes


def _mounted_tape_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tape_by_id = {
        tape["id"]: tape["barcode"]
        for tape in db.list_tapes(config, include_ignored=True)
        if tape.get("id") is not None
    }
    mounted: dict[str, dict[str, Any]] = {}
    for drive in db.list_drives(config):
        barcode = tape_by_id.get(drive.get("loaded_tape_id"))
        mount_path = drive.get("mount_path")
        if barcode is None or mount_path is None:
            continue
        if _is_mounted(mount_path):
            mounted[barcode] = {
                "drive": drive["id"],
                "mount_path": mount_path,
            }
    return mounted


def _loaded_tape_map(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tape_by_id = {
        tape["id"]: tape["barcode"]
        for tape in db.list_tapes(config, include_ignored=True)
        if tape.get("id") is not None
    }
    loaded: dict[str, dict[str, Any]] = {}
    for drive in db.list_drives(config):
        barcode = tape_by_id.get(drive.get("loaded_tape_id"))
        if barcode is None:
            continue
        loaded[barcode] = {
            "drive": drive["id"],
            "mount_path": drive.get("mount_path"),
        }
    return loaded


def _empty_drive(config: dict[str, Any]) -> dict[str, Any] | None:
    for drive in db.list_drives(config):
        if drive.get("loaded_tape_id") is None or drive.get("state") == "empty":
            return drive
    return None


def _is_mounted(path: str) -> bool:
    completed = subprocess.run(
        ["findmnt", "-n", "--output", "TARGET", "--target", path],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        return False
    return completed.stdout.decode().strip() == path


def _run_mounted_retrieve_job(
    config: dict[str, Any], job: dict[str, Any], mount_map: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    copy_plan = _mounted_retrieve_copy_plan(job, mount_map)
    _preflight_copy_plan(copy_plan)

    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job["id"],
                "running",
                event_type="retrieve_job_started",
                message="Mounted-only retrieve job started.",
                data={
                    "file_count": len(copy_plan),
                    "tapes": _required_retrieve_tapes(job),
                },
            )

    copied_files = _copy_retrieve_entries(config, job["id"], copy_plan)

    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job["id"],
                "complete",
                event_type="job_complete",
                message="Mounted-only retrieve job completed.",
                data={"copied_files": copied_files},
            )
            complete_job = db.get_job(connection, job["id"])

    return {
        "ran": True,
        "job": complete_job,
        "state": "complete",
        "message": "Mounted-only retrieve job completed.",
        "copied_files": copied_files,
        "blocked_tapes": [],
    }


class _SchedulerBlocked(RuntimeError):
    def __init__(self, state: str, message: str, data: dict[str, Any]) -> None:
        super().__init__(message)
        self.state = state
        self.data = data


def _run_automatic_retrieve_job(
    config: dict[str, Any], job: dict[str, Any]
) -> dict[str, Any]:
    copied_files: list[dict[str, Any]] = []

    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job["id"],
                "running",
                event_type="retrieve_scheduler_started",
                message="Automatic retrieve scheduler started.",
                data={"required_tapes": _required_retrieve_tapes(job)},
            )

    try:
        groups = (job.get("target") or {}).get("groups", [])
        for index, group in enumerate(groups):
            tape_barcode = group.get("tape_barcode")
            if not isinstance(tape_barcode, str) or tape_barcode == "":
                raise executor.ExecutionError(
                    "Retrieve job has a group without a tape barcode."
                )

            try:
                mount_info = _ensure_retrieve_tape_mounted(config, job, tape_barcode)
            except _SchedulerBlocked as blocked:
                with closing(db.connect(config)) as connection:
                    with connection:
                        db.transition_job(
                            connection,
                            job["id"],
                            blocked.state,
                            event_type="retrieve_scheduler_blocked",
                            message=str(blocked),
                            data=blocked.data,
                        )
                        updated_job = db.get_job(connection, job["id"])
                return {
                    "ran": False,
                    "job": updated_job,
                    "state": blocked.state,
                    "message": str(blocked),
                    "copied_files": copied_files,
                    "blocked_tapes": blocked.data.get("blocked_tapes", []),
                }

            copy_plan = _mounted_retrieve_copy_plan(
                {"target": {"groups": [group]}},
                {tape_barcode: mount_info},
            )
            _preflight_copy_plan(copy_plan)
            copied_files.extend(_copy_retrieve_entries(config, job["id"], copy_plan))

            more_groups = index < len(groups) - 1
            should_unload = (
                mount_info.get("prepared_by_scheduler")
                and (
                    more_groups
                    or bool(config.get("scheduler", {}).get("unloadAfterRetrieve", False))
                )
            )
            if should_unload:
                _release_scheduler_drive(config, job, mount_info["drive"], tape_barcode)

        with closing(db.connect(config)) as connection:
            with connection:
                db.transition_job(
                    connection,
                    job["id"],
                    "complete",
                    event_type="job_complete",
                    message="Automatic retrieve job completed.",
                    data={"copied_files": copied_files},
                )
                complete_job = db.get_job(connection, job["id"])

        return {
            "ran": True,
            "job": complete_job,
            "state": "complete",
            "message": "Automatic retrieve job completed.",
            "copied_files": copied_files,
            "blocked_tapes": [],
        }
    except executor.ExecutionError as exc:
        _fail_job_for_queue(config, job["id"], str(exc))
        failed_job = db.get_job_by_id(config, job["id"])
        return {
            "ran": True,
            "job": failed_job,
            "state": "failed",
            "message": str(exc),
            "copied_files": copied_files,
            "blocked_tapes": [],
        }


def _ensure_retrieve_tape_mounted(
    config: dict[str, Any], job: dict[str, Any], tape_barcode: str
) -> dict[str, Any]:
    mounted = _mounted_tape_map(config)
    if tape_barcode in mounted:
        return {**mounted[tape_barcode], "prepared_by_scheduler": False}

    loaded = _loaded_tape_map(config)
    if tape_barcode in loaded:
        drive_name = loaded[tape_barcode]["drive"]
        with closing(db.connect(config)) as connection:
            with connection:
                db.transition_job(
                    connection,
                    job["id"],
                    "mounting_ltfs",
                    event_type="retrieve_mounting_ltfs",
                    message="Mounting already-loaded tape for automatic retrieve.",
                    data={"tape_barcode": tape_barcode, "drive": drive_name},
                )
        executor.mount_ltfs(config, drive_name, read_only=True)
        mount_path = loaded[tape_barcode].get("mount_path") or _drive_mount_path(
            config, drive_name
        )
        if not mount_path or not _is_mounted(mount_path):
            raise _SchedulerBlocked(
                "waiting_for_mount",
                f"Tape {tape_barcode} was mounted by command, but no LTFS mount is visible yet.",
                {"blocked_tapes": [tape_barcode], "drive": drive_name},
            )
        return {
            "drive": drive_name,
            "mount_path": mount_path,
            "prepared_by_scheduler": True,
        }

    drive = _empty_drive(config)
    if drive is None:
        raise _SchedulerBlocked(
            "waiting_for_drive",
            "No empty configured drive is available for automatic retrieve.",
            {"blocked_tapes": [tape_barcode]},
        )

    drive_name = drive["id"]
    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job["id"],
                "waiting_for_changer",
                event_type="retrieve_waiting_for_changer",
                message="Waiting for changer lock to load retrieve tape.",
                data={"tape_barcode": tape_barcode, "drive": drive_name},
            )
            db.transition_job(
                connection,
                job["id"],
                "loading_tape",
                event_type="retrieve_loading_tape",
                message="Loading tape for automatic retrieve.",
                data={"tape_barcode": tape_barcode, "drive": drive_name},
            )
    executor.load_tape(config, tape_barcode, drive_name)

    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job["id"],
                "mounting_ltfs",
                event_type="retrieve_mounting_ltfs",
                message="Mounting tape read-only for automatic retrieve.",
                data={"tape_barcode": tape_barcode, "drive": drive_name},
            )
    executor.mount_ltfs(config, drive_name, read_only=True)

    mount_path = drive.get("mount_path") or _drive_mount_path(config, drive_name)
    if not mount_path or not _is_mounted(mount_path):
        raise _SchedulerBlocked(
            "waiting_for_mount",
            f"Tape {tape_barcode} was loaded, but no LTFS mount is visible yet.",
            {"blocked_tapes": [tape_barcode], "drive": drive_name},
        )

    return {
        "drive": drive_name,
        "mount_path": mount_path,
        "prepared_by_scheduler": True,
    }


def _drive_mount_path(config: dict[str, Any], drive_name: str) -> str | None:
    drive = db.get_drive(config, drive_name)
    if drive is not None and drive.get("mount_path"):
        return drive["mount_path"]
    for drive_cfg in config.get("library", {}).get("drives", []):
        if drive_cfg.get("name") == drive_name:
            return drive_cfg.get("mountPath")
    return None


def _release_scheduler_drive(
    config: dict[str, Any], job: dict[str, Any], drive_name: str, tape_barcode: str
) -> None:
    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job["id"],
                "unmounting",
                event_type="retrieve_unmounting_ltfs",
                message="Unmounting scheduler-mounted tape after retrieve.",
                data={"tape_barcode": tape_barcode, "drive": drive_name},
            )
    executor.unmount_ltfs(config, drive_name)
    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job["id"],
                "unloading",
                event_type="retrieve_unloading_tape",
                message="Unloading scheduler-mounted tape after retrieve.",
                data={"tape_barcode": tape_barcode, "drive": drive_name},
            )
    executor.unload_tape(config, drive_name)


def _mounted_retrieve_copy_plan(
    job: dict[str, Any], mount_map: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    copy_plan: list[dict[str, Any]] = []
    for group in (job.get("target") or {}).get("groups", []):
        tape_barcode = group.get("tape_barcode")
        if tape_barcode not in mount_map:
            raise executor.ExecutionError(f"Tape {tape_barcode} is not mounted.")
        mount_path = Path(mount_map[tape_barcode]["mount_path"])
        for file_entry in group.get("files", []):
            archive_path = _clean_archive_path(file_entry["archive_path"])
            destination_path = Path(file_entry["destination_path"])
            copy_plan.append(
                {
                    "tape_barcode": tape_barcode,
                    "archive_path": archive_path,
                    "source_path": mount_path / archive_path,
                    "destination_path": destination_path,
                    "size_bytes": int(file_entry.get("size_bytes") or 0),
                    "checksum_sha256": file_entry.get("checksum_sha256"),
                }
            )
    return copy_plan


def _preflight_copy_plan(copy_plan: list[dict[str, Any]]) -> None:
    for entry in copy_plan:
        source_path = entry["source_path"]
        destination_path = entry["destination_path"]
        if destination_path.exists():
            if not destination_path.is_file():
                raise executor.ExecutionError(
                    f"Destination already exists and is not a file: {destination_path}"
                )
            expected_size = int(entry.get("size_bytes") or 0)
            actual_size = destination_path.stat().st_size
            expected_checksum = entry.get("checksum_sha256")
            if actual_size == expected_size and (
                not expected_checksum
                or _checksum_sha256(destination_path) == expected_checksum
            ):
                entry["skip_existing"] = True
            else:
                raise executor.ExecutionError(
                    f"Destination already exists with different contents: {destination_path}"
                )
        if not source_path.is_file():
            raise executor.ExecutionError(f"Mounted source file is missing: {source_path}")


def _copy_retrieve_entries(
    config: dict[str, Any], job_id: str, copy_plan: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    copied_files: list[dict[str, Any]] = []
    for entry in copy_plan:
        with closing(db.connect(config)) as connection:
            with connection:
                db.append_job_event(
                    connection,
                    job_id,
                    "retrieve_file_started",
                    "Started copying a file from mounted LTFS.",
                    {
                        "tape_barcode": entry["tape_barcode"],
                        "archive_path": entry["archive_path"],
                        "source_path": str(entry["source_path"]),
                        "destination_path": str(entry["destination_path"]),
                    },
                )

        skipped = bool(entry.get("skip_existing"))
        if not skipped:
            _copy_retrieve_file(entry["source_path"], entry["destination_path"])

        copied_file = {
            "tape_barcode": entry["tape_barcode"],
            "archive_path": entry["archive_path"],
            "source_path": str(entry["source_path"]),
            "destination_path": str(entry["destination_path"]),
            "size_bytes": entry["size_bytes"],
            "skipped_existing": skipped,
        }
        copied_files.append(copied_file)

        with closing(db.connect(config)) as connection:
            with connection:
                db.append_job_event(
                    connection,
                    job_id,
                    "retrieve_file_complete" if not skipped else "retrieve_file_skipped",
                    (
                        "Completed copying a file from mounted LTFS."
                        if not skipped
                        else "Destination already matched; skipped copy."
                    ),
                    copied_file,
                )
    return copied_files


def _copy_retrieve_file(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        raise executor.ExecutionError(
            f"Destination already exists and will not be overwritten: {destination_path}"
        )
    temp_path = destination_path.with_name(
        f".{destination_path.name}.tapelib-{uuid.uuid4().hex}.tmp"
    )
    try:
        shutil.copy2(source_path, temp_path)
        os.replace(temp_path, destination_path)
    except OSError as exc:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise executor.ExecutionError(
            f"Failed copying {source_path} to {destination_path}: {exc}"
        ) from exc


def _fail_job_for_queue(config: dict[str, Any], job_id: str, message: str) -> None:
    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job_id,
                "failed",
                event_type="job_failed",
                message=message,
                last_error=message,
            )


def _command_jobs(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    print(
        json.dumps(
            db.list_jobs(config, state=args.state, limit=args.limit),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _command_job_status(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    try:
        payload = job_status.snapshot(config, args.job_id, event_limit=args.event_limit)
    except KeyError as exc:
        raise executor.ExecutionError(f"Unknown job id: {args.job_id}") from exc
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _command_journal(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    print(
        json.dumps(
            db.list_job_events(config, job_id=args.job_id, limit=args.limit),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _command_load_tape(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    job = executor.load_tape(config, args.barcode, args.drive)
    print(json.dumps(job, indent=2, sort_keys=True))
    return 0


def _command_unload_tape(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    job = executor.unload_tape(config, args.drive, destination_slot=args.slot)
    print(json.dumps(job, indent=2, sort_keys=True))
    return 0


def _command_mount_ltfs(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    job = executor.mount_ltfs(config, args.drive, read_only=not args.read_write)
    print(json.dumps(job, indent=2, sort_keys=True))
    return 0


def _command_unmount_ltfs(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    job = executor.unmount_ltfs(config, args.drive)
    print(json.dumps(job, indent=2, sort_keys=True))
    return 0


def _command_reconcile_hardware(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    print(
        json.dumps(
            {"reconciled": executor.reconcile_hardware_jobs(config)},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _library_inventory_manifest(config: dict[str, Any]) -> dict[str, Any]:
    db.initialize_database(config)
    return {
        "format": "tapelib-library-inventory-v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "conflict_policy": {
            "mode": "additive_latest_observation_wins",
            "notes": "Tape-carried manifests are advisory snapshots. Importing an older manifest must not delete or downgrade newer catalog data.",
        },
        "library": _readable_inventory(config),
        "tapes": db.list_tapes(config, include_ignored=True),
        "drives": db.list_drives(config),
        "files": db.list_files(config),
    }


def _command_inventory_manifest(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    manifest = _library_inventory_manifest(config)
    body = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(body, encoding="utf-8")
    print(body, end="")
    return 0


def _logical_unit_for_file(root: Path, file_path: Path) -> tuple[str, str]:
    relative_parts = file_path.relative_to(root).parts
    if len(relative_parts) >= 4 and relative_parts[:3] == (
        "wishlist",
        "shared",
        "best-50-by-console",
    ):
        unit_parts = relative_parts[:4]
    elif len(relative_parts) >= 3 and relative_parts[0] == "wishlist":
        unit_parts = relative_parts[:3]
    elif len(relative_parts) >= 2:
        unit_parts = relative_parts[:-1]
    else:
        unit_parts = relative_parts[:-1] or relative_parts

    unit_path = "/".join(unit_parts)
    file_logical_path = "/".join(relative_parts)
    return unit_path, file_logical_path


@dataclass
class PlannedFile:
    source_path: str
    logical_path: str
    size_bytes: int


@dataclass
class PlannedUnit:
    unit_path: str
    files: list[PlannedFile]

    @property
    def size_bytes(self) -> int:
        return sum(file.size_bytes for file in self.files)


def _scan_game_units(config: dict[str, Any]) -> list[PlannedUnit]:
    roots = [Path(root) for root in config.get("games", {}).get("sourceRoots", [])]
    units: dict[str, list[PlannedFile]] = {}

    for root in roots:
        if not root.exists():
            continue
        for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
            unit_path, logical_path = _logical_unit_for_file(root, file_path)
            units.setdefault(unit_path, []).append(
                PlannedFile(
                    source_path=str(file_path),
                    logical_path=logical_path,
                    size_bytes=file_path.stat().st_size,
                )
            )

    return [
        PlannedUnit(unit_path=unit_path, files=files)
        for unit_path, files in sorted(units.items())
    ]


def _split_unit_files(
    unit: PlannedUnit,
    tape_names: list[str],
    current_tape_index: int,
    current_remaining_bytes: int,
    tape_capacity_bytes: int,
) -> tuple[list[dict[str, Any]], int, int]:
    assignments: list[dict[str, Any]] = []
    chunk_files: list[dict[str, Any]] = []
    chunk_size = 0
    split_index = 1

    for planned_file in unit.files:
        file_payload = asdict(planned_file)
        if planned_file.size_bytes > tape_capacity_bytes:
            raise ValueError(
                f"File '{planned_file.source_path}' exceeds the configured tape capacity and cannot be planned safely."
            )

        if planned_file.size_bytes > current_remaining_bytes and chunk_files:
            assignments.append(
                {
                    "tape": tape_names[current_tape_index],
                    "unit_path": unit.unit_path,
                    "size_bytes": chunk_size,
                    "split": {
                        "enabled": True,
                        "part": split_index,
                    },
                    "files": chunk_files,
                }
            )
            current_tape_index += 1
            if current_tape_index >= len(tape_names):
                raise ValueError(
                    "Not enough selected tapes to fit the planned backup set."
                )
            current_remaining_bytes = tape_capacity_bytes
            chunk_files = []
            chunk_size = 0
            split_index += 1

        if planned_file.size_bytes > current_remaining_bytes and not chunk_files:
            current_tape_index += 1
            if current_tape_index >= len(tape_names):
                raise ValueError(
                    "Not enough selected tapes to fit the planned backup set."
                )
            current_remaining_bytes = tape_capacity_bytes

        chunk_files.append(file_payload)
        chunk_size += planned_file.size_bytes
        current_remaining_bytes -= planned_file.size_bytes

    if chunk_files:
        assignments.append(
            {
                "tape": tape_names[current_tape_index],
                "unit_path": unit.unit_path,
                "size_bytes": chunk_size,
                "split": {
                    "enabled": split_index > 1,
                    "part": split_index,
                },
                "files": chunk_files,
            }
        )

    return assignments, current_tape_index, current_remaining_bytes


def _atomic_unit_assignment(unit: PlannedUnit, tape: str) -> dict[str, Any]:
    return {
        "tape": tape,
        "unit_path": unit.unit_path,
        "size_bytes": unit.size_bytes,
        "split": {
            "enabled": False,
            "part": 1,
        },
        "files": [asdict(file) for file in unit.files],
    }


def _pack_atomic_units_first_fit_decreasing(
    units: list[PlannedUnit],
    tape_names: list[str],
    tape_capacity_bytes: int,
) -> list[dict[str, Any]]:
    remaining_by_tape = [tape_capacity_bytes for _tape in tape_names]
    assignments_by_tape: list[list[dict[str, Any]]] = [
        [] for _tape in tape_names
    ]
    original_order = {unit.unit_path: index for index, unit in enumerate(units)}

    sorted_units = sorted(
        units,
        key=lambda unit: (-unit.size_bytes, original_order[unit.unit_path]),
    )
    for unit in sorted_units:
        for tape_index, remaining_bytes in enumerate(remaining_by_tape):
            if unit.size_bytes <= remaining_bytes:
                assignments_by_tape[tape_index].append(
                    _atomic_unit_assignment(unit, tape_names[tape_index])
                )
                remaining_by_tape[tape_index] -= unit.size_bytes
                break
        else:
            raise ValueError("Not enough selected tapes to fit the planned backup set.")

    assignments: list[dict[str, Any]] = []
    for tape_assignments in assignments_by_tape:
        assignments.extend(tape_assignments)
    return assignments


def _plan_game_backup_sequential(
    units: list[PlannedUnit],
    tape_names: list[str],
    tape_capacity_bytes: int,
) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    current_tape_index = 0
    current_remaining_bytes = tape_capacity_bytes

    for unit in units:
        unit_size = unit.size_bytes
        if unit_size <= current_remaining_bytes:
            assignments.append(
                _atomic_unit_assignment(unit, tape_names[current_tape_index])
            )
            current_remaining_bytes -= unit_size
            continue

        if unit_size <= tape_capacity_bytes:
            current_tape_index += 1
            if current_tape_index >= len(tape_names):
                raise ValueError(
                    "Not enough selected tapes to fit the planned backup set."
            )
            current_remaining_bytes = tape_capacity_bytes
            assignments.append(
                _atomic_unit_assignment(unit, tape_names[current_tape_index])
            )
            current_remaining_bytes -= unit_size
            continue

        split_assignments, current_tape_index, current_remaining_bytes = (
            _split_unit_files(
                unit,
                tape_names,
                current_tape_index,
                current_remaining_bytes,
                tape_capacity_bytes,
            )
        )
        assignments.extend(split_assignments)

    return assignments


def _game_tape_specs(config: dict[str, Any]) -> list[dict[str, Any]]:
    selected_tapes = config.get("games", {}).get("selectedTapes", [])
    specs: list[dict[str, Any]] = []

    for entry in selected_tapes:
        if isinstance(entry, str) and entry.strip():
            specs.append({"barcode": entry.strip()})
            continue
        if isinstance(entry, dict):
            barcode = entry.get("barcode")
            if isinstance(barcode, str) and barcode.strip():
                specs.append(dict(entry))
                continue
        raise ValueError(
            "games.selectedTapes entries must be either tape barcode strings or "
            "attribute sets with at least a 'barcode' field."
        )

    return specs


def _plan_game_backup(config: dict[str, Any]) -> dict[str, Any]:
    games = config.get("games", {})
    tape_specs = _game_tape_specs(config)
    tape_names = [spec["barcode"] for spec in tape_specs]
    tape_capacity_bytes = int(games.get("tapeCapacityBytes", 0))
    units = _scan_game_units(config)

    if tape_capacity_bytes <= 0:
        raise ValueError("games.tapeCapacityBytes must be set to a positive integer.")
    if tape_names == []:
        raise ValueError(
            "games.selectedTapes must contain at least one tape barcode for planning."
        )

    if any(unit.size_bytes > tape_capacity_bytes for unit in units):
        assignments = _plan_game_backup_sequential(
            units,
            tape_names,
            tape_capacity_bytes,
        )
    else:
        assignments = _pack_atomic_units_first_fit_decreasing(
            units,
            tape_names,
            tape_capacity_bytes,
        )

    tape_metadata = {
        spec["barcode"]: {
            key: value
            for key, value in spec.items()
            if key != "barcode"
        }
        for spec in tape_specs
    }
    assignments = [
        dict(assignment, **tape_metadata.get(assignment["tape"], {}))
        for assignment in assignments
    ]

    per_tape: dict[str, dict[str, Any]] = {}
    for assignment in assignments:
        tape_summary = per_tape.setdefault(
            assignment["tape"],
            {
                "tape": assignment["tape"],
                "units": [],
                "size_bytes": 0,
                **tape_metadata.get(assignment["tape"], {}),
            },
        )
        tape_summary["units"].append(
            {
                "unit_path": assignment["unit_path"],
                "size_bytes": assignment["size_bytes"],
                "split": assignment["split"],
            }
        )
        tape_summary["size_bytes"] += assignment["size_bytes"]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "namespace_prefix": games.get("namespacePrefix", "/games"),
        "source_roots": games.get("sourceRoots", []),
        "selected_tapes": tape_specs,
        "tape_capacity_bytes": tape_capacity_bytes,
        "unit_count": len(units),
        "units": [
            {
                "unit_path": unit.unit_path,
                "size_bytes": unit.size_bytes,
                "file_count": len(unit.files),
            }
            for unit in units
        ],
        "assignments": assignments,
        "tapes": list(per_tape.values()),
    }


def _command_plan_games_backup(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    plan = _plan_game_backup(config)
    if args.write_status:
        _write_json(_state_dir(config) / "status" / "latest-plan.json", plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    return 0


def _normalized_namespace(value: str | None) -> str:
    return (value or "").strip("/") or "games"


def _game_namespace(config: dict[str, Any]) -> str:
    return _normalized_namespace(config.get("games", {}).get("namespacePrefix", "/games"))


def _is_game_write_job(job: dict[str, Any], namespace: str) -> bool:
    if job.get("type") != WRITE_ARCHIVE_JOB_TYPE:
        return False
    target = job.get("target") or {}
    source = job.get("source") or {}
    target_namespace = _normalized_namespace(target.get("namespace_prefix"))
    source_namespace = _normalized_namespace(source.get("namespace_prefix"))
    return namespace in {target_namespace, source_namespace}


def _game_write_jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    namespace = _game_namespace(config)
    jobs = db.list_jobs(config, limit=10000)
    return [job for job in jobs if _is_game_write_job(job, namespace)]


def _job_file_count(job: dict[str, Any]) -> int:
    files = (job.get("source") or {}).get("files", [])
    return len(files) if isinstance(files, list) else 0


def _job_bytes(job: dict[str, Any]) -> int:
    if job.get("required_bytes") is not None:
        return int(job["required_bytes"])
    source = job.get("source") or {}
    if source.get("batch_bytes") is not None:
        return int(source["batch_bytes"])
    files = source.get("files", [])
    if not isinstance(files, list):
        return 0
    return sum(int(file.get("size_bytes") or 0) for file in files)


def _job_tape(job: dict[str, Any]) -> str | None:
    target = job.get("target") or {}
    tape = target.get("tape_barcode")
    return tape if isinstance(tape, str) and tape else None


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _plan_tape_summaries(plan: dict[str, Any]) -> list[dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for assignment in plan.get("assignments", []):
        tape = str(assignment.get("tape") or "")
        if not tape:
            continue
        summary = summaries.setdefault(
            tape,
            {
                "tape": tape,
                "units": 0,
                "file_count": 0,
                "size_bytes": 0,
            },
        )
        summary["units"] += 1
        files = assignment.get("files", [])
        summary["file_count"] += len(files) if isinstance(files, list) else 0
        summary["size_bytes"] += int(assignment.get("size_bytes") or 0)

    selected_tapes = [str(tape) for tape in plan.get("selected_tapes", [])]
    order = {tape: index for index, tape in enumerate(selected_tapes)}
    return sorted(
        summaries.values(),
        key=lambda item: (order.get(item["tape"], len(order)), item["tape"]),
    )


def _games_backup_progress_payload(
    config: dict[str, Any], *, include_plan: bool = True
) -> dict[str, Any]:
    jobs = sorted(_game_write_jobs(config), key=lambda job: job.get("created_at") or "")
    completed_jobs = [job for job in jobs if job.get("state") == "complete"]
    active_jobs = [
        job for job in jobs if job_status.bucket_for_state(str(job.get("state"))) == "active"
    ]
    waiting_jobs = [
        job
        for job in jobs
        if job_status.bucket_for_state(str(job.get("state"))) == "waiting"
    ]
    queued_jobs = [
        job for job in jobs if job_status.bucket_for_state(str(job.get("state"))) == "queued"
    ]
    problem_jobs = [
        job for job in jobs if job.get("state") in {"failed", "needs_operator"}
    ]
    next_job = (active_jobs or waiting_jobs or queued_jobs or [None])[0]

    plan = _plan_game_backup(config) if include_plan else None
    plan_tapes = _plan_tape_summaries(plan) if plan is not None else []

    status = "active" if active_jobs else "inactive"
    if active_jobs:
        reason = "a game archive write is currently running."
    elif problem_jobs:
        reason = "a game archive write needs operator attention."
    elif waiting_jobs:
        reason = "the next game archive write is waiting for the target tape to be mounted read-write."
    elif queued_jobs:
        reason = "the next game archive write is queued and has not started."
    elif plan_tapes:
        reason = "no game archive write job is queued; stage the next cache wave before writing."
    elif not include_plan:
        reason = (
            "no game archive write job is queued; stage the next cache wave "
            "before writing, or use --plan for a fresh source scan."
        )
    else:
        reason = "no game archive plan or write jobs were found."

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "active": bool(active_jobs),
        "status": status,
        "reason": reason,
        "written_tapes": _ordered_unique(
            [tape for tape in (_job_tape(job) for job in completed_jobs) if tape]
        ),
        "completed_batches": len(completed_jobs),
        "written_file_count": sum(_job_file_count(job) for job in completed_jobs),
        "written_bytes": sum(_job_bytes(job) for job in completed_jobs),
        "next_job": _summarize_game_job(next_job) if next_job is not None else None,
        "active_jobs": [_summarize_game_job(job) for job in active_jobs],
        "waiting_jobs": [_summarize_game_job(job) for job in waiting_jobs],
        "queued_jobs": [_summarize_game_job(job) for job in queued_jobs],
        "problem_jobs": [_summarize_game_job(job) for job in problem_jobs],
        "plan": {
            "tape_count": len(plan_tapes),
            "tapes": plan_tapes,
            "total_file_count": sum(tape["file_count"] for tape in plan_tapes),
            "total_bytes": sum(tape["size_bytes"] for tape in plan_tapes),
        }
        if plan is not None
        else None,
    }


def _summarize_game_job(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if job is None:
        return None
    return {
        "id": job["id"],
        "state": job["state"],
        "bucket": job_status.bucket_for_state(str(job.get("state"))),
        "tape": _job_tape(job),
        "file_count": _job_file_count(job),
        "bytes": _job_bytes(job),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "last_error": job.get("last_error"),
    }


def _render_games_backup_progress(payload: dict[str, Any]) -> str:
    active_label = "YES" if payload["active"] else "NO"
    lines = [
        f"Game library backup active: {active_label}",
        f"Status: {payload['reason']}",
        "",
        "Tape actually written so far: "
        + (", ".join(payload["written_tapes"]) if payload["written_tapes"] else "none"),
        f"Completed game archive writes: {_format_int(payload['completed_batches'])} batches",
        (
            "Written: "
            f"{_format_int(payload['written_file_count'])} game files, "
            f"about {_format_gib(payload['written_bytes'])}"
        ),
    ]

    next_job = payload.get("next_job")
    if next_job is not None:
        state_label = {
            "active": "Active write",
            "waiting": "Next write waiting",
            "queued": "Queued next write",
            "failed": "Problem write",
        }.get(next_job.get("bucket"), "Next write")
        tape = next_job.get("tape") or "unknown tape"
        also = f", also for {tape}" if tape in payload["written_tapes"] else f", for {tape}"
        lines.extend(
            [
                (
                    f"{state_label}: {_format_int(next_job['file_count'])} files, "
                    f"about {_format_gib(next_job['bytes'])}{also}"
                ),
                f"Next job: {next_job['id']} ({next_job['state']})",
            ]
        )
        if next_job.get("bucket") in {"queued", "waiting"}:
            lines.append(
                "Command to continue: "
                "tapelib --config /etc/tapelib/config.json games-backup-run-next --resume"
            )
            lines.append(
                "Manual equivalent: "
                f"tapelib --config /etc/tapelib/config.json write-archive "
                f"--job-id {next_job['id']} --resume"
            )

    plan = payload.get("plan")
    if plan is not None:
        lines.extend(["", f"The full current plan uses {plan['tape_count']} tapes:", ""])
        for tape in plan["tapes"]:
            lines.append(
                f"{tape['tape']:<9} - "
                f"{_format_int(tape['units'])} planned units, "
                f"{_format_int(tape['file_count']):>5} files, "
                f"about {_format_gib(tape['size_bytes'], digits=1)}"
            )

    return "\n".join(lines) + "\n"


def _command_games_backup_status(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    include_plan = bool(getattr(args, "plan", False)) and not args.no_plan
    payload = _games_backup_progress_payload(config, include_plan=include_plan)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(_render_games_backup_progress(payload), end="")
    return 0


def _command_games_backup_run_next(args: argparse.Namespace) -> int:
    from . import archive as _archive

    config = _load_config(Path(args.config))
    jobs = sorted(_game_write_jobs(config), key=lambda job: job.get("created_at") or "")
    active_jobs = [
        job for job in jobs if job_status.bucket_for_state(str(job.get("state"))) == "active"
    ]
    if active_jobs:
        raise executor.ExecutionError(
            f"Game backup is already active in job {active_jobs[0]['id']}."
        )

    runnable_states = {"queued", "waiting_for_mount"}
    if args.resume:
        runnable_states |= {"failed", "needs_operator"}
    next_job = next((job for job in jobs if job.get("state") in runnable_states), None)
    if next_job is None:
        raise executor.ExecutionError(
            "No runnable game archive write job found. Run "
            "'tapelib stage-games-backup' to stage the next cache wave."
        )

    try:
        result = _archive.write_staged_archive(config, next_job, resume=args.resume)
    except _archive.ArchiveError as exc:
        raise executor.ExecutionError(str(exc)) from exc

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        tape = _job_tape(result) or _job_tape(next_job) or "unknown tape"
        print(
            "Completed game archive write: "
            f"{result['id']} on {tape} "
            f"({_format_int(_job_file_count(result))} files, "
            f"about {_format_gib(_job_bytes(result))})"
        )
    return 0


def _command_index_tape(args: argparse.Namespace) -> int:
    """Walk a mounted LTFS tape and update the file catalog."""
    config = _load_config(Path(args.config))
    resolved_barcode, resolved_mount, _resolved_drive = _resolve_tape_target(
        config,
        args.barcode_or_drive,
        require_mounted=True,
    )

    try:
        result = db.index_tape(config, resolved_barcode, resolved_mount)
    except ValueError as exc:
        raise executor.ExecutionError(str(exc)) from exc

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _command_stage_games_backup(args: argparse.Namespace) -> int:
    """Stage game archive files to the local cache, creating write_archive jobs."""
    from . import archive as _archive

    config = _load_config(Path(args.config))

    if args.plan_file:
        plan_path = Path(args.plan_file)
        if not plan_path.exists():
            raise executor.ExecutionError(
                f"Plan file not found: {plan_path}"
            )
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise executor.ExecutionError(
                f"Plan file is not valid JSON: {exc}"
            ) from exc
    else:
        plan = _plan_game_backup(config)

    # Optional tape filter — stage only one tape's worth at a time.
    if getattr(args, "tape", None):
        tape_filter = args.tape.upper()
        filtered = [a for a in plan.get("assignments", []) if a["tape"] == tape_filter]
        if not filtered:
            raise executor.ExecutionError(
                f"No assignments found for tape '{tape_filter}' in the plan. "
                f"Available tapes: {sorted({a['tape'] for a in plan.get('assignments', [])})}"
            )
        plan = dict(plan, assignments=filtered)

    # Warn if the plan is likely to exceed available cache space.
    cache_cfg = config.get("cache", {})
    cache_path = Path(cache_cfg.get("path", "/run/media/ash/cache/tapelib"))
    reserved_raw = cache_cfg.get("reservedFreeBytes", 0)
    reserved = _parse_size_string(reserved_raw) if isinstance(reserved_raw, str) else int(reserved_raw)
    try:
        st = os.statvfs(cache_path)
        free_bytes = st.f_bavail * st.f_frsize - reserved
        plan_bytes = sum(a.get("size_bytes", 0) for a in plan.get("assignments", []))
        if plan_bytes > free_bytes:
            needed_gb = plan_bytes / 1e9
            free_gb = free_bytes / 1e9
            import sys as _sys
            print(
                f"WARNING: plan needs {needed_gb:.1f} GB but only {free_gb:.1f} GB "
                f"cache space is available. Use --tape BARCODE to stage one tape at a time.",
                file=_sys.stderr,
            )
    except OSError:
        pass

    max_staged_bytes = None
    if getattr(args, "max_staged_bytes", None):
        max_staged_bytes = _parse_size_string(args.max_staged_bytes)

    try:
        jobs = _archive.stage_games_archive(
            config,
            plan,
            max_staged_bytes=max_staged_bytes,
        )
    except _archive.ArchiveError as exc:
        raise executor.ExecutionError(str(exc)) from exc

    staged_bytes = sum(
        int(job.get("required_bytes") or 0)
        for job in jobs
    )
    payload = {
        "staged_jobs": jobs,
        "job_count": len(jobs),
        "staged_bytes": staged_bytes,
        "message": (
            "Files staged to cache. Run 'tapelib write-archive --job-id <id>' "
            "after mounting each target tape read-write. By default this fills the "
            "currently available cache budget, and write-archive now drains staged "
            "files incrementally so later stage-games-backup runs can refill the "
            "next wave without duplicating queued or already written files."
        ),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _command_write_archive(args: argparse.Namespace) -> int:
    """Write a staged write_archive job's files to the mounted LTFS tape."""
    from . import archive as _archive

    config = _load_config(Path(args.config))

    try:
        job = db.get_job_by_id(config, args.job_id)
    except KeyError as exc:
        raise executor.ExecutionError(
            f"Unknown job id: {args.job_id}"
        ) from exc

    try:
        result = _archive.write_staged_archive(config, job, resume=args.resume)
    except _archive.ArchiveError as exc:
        raise executor.ExecutionError(str(exc)) from exc

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _command_promote_ingest(args: argparse.Namespace) -> int:
    from . import archive as _archive

    config = _load_config(Path(args.config))
    try:
        job = db.get_job_by_id(config, args.job_id)
    except KeyError as exc:
        raise executor.ExecutionError(
            f"Unknown ingest job id: {args.job_id}"
        ) from exc

    try:
        result = _archive.promote_cached_ingest(
            config,
            job,
            tape_barcode=args.tape,
            namespace_prefix=args.namespace,
        )
    except _archive.ArchiveError as exc:
        raise executor.ExecutionError(str(exc)) from exc

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _command_doctor(args: argparse.Namespace) -> int:
    """Print a diagnostic report: drives, mounts, locks, active jobs, cache."""
    config = _load_config(Path(args.config))

    report: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "drives": [],
        "locks": [],
        "active_jobs": [],
        "needs_operator_jobs": [],
        "queued_write_archive_jobs": [],
        "cache": {},
        "warnings": [],
    }

    # Drive and mount state.
    try:
        drives = db.list_drives(config)
        tape_by_id = {
            t["id"]: t["barcode"]
            for t in db.list_tapes(config, include_ignored=True)
            if t.get("id") is not None
        }
        for drive in drives:
            mount_path = drive.get("mount_path")
            mounted = _is_mounted(mount_path) if mount_path else False
            loaded_barcode = tape_by_id.get(drive.get("loaded_tape_id"))
            entry = {
                "id": drive["id"],
                "db_state": drive.get("state"),
                "loaded_tape": loaded_barcode,
                "mount_path": mount_path,
                "ltfs_mounted": mounted,
            }
            report["drives"].append(entry)
            if drive.get("state") == "full" and not mounted:
                report["warnings"].append(
                    f"Drive {drive['id']!r} has a tape loaded but LTFS is not mounted."
                )
    except Exception as exc:
        report["warnings"].append(f"Could not read drive state from DB: {exc}")

    # Lock files.
    state_dir = _state_dir(config)
    lock_dir = state_dir / "locks"
    try:
        if lock_dir.exists():
            for lock_file in sorted(lock_dir.glob("*.lock")):
                st = lock_file.stat()
                report["locks"].append(
                    {
                        "name": lock_file.stem,
                        "path": str(lock_file),
                        "mtime": time.strftime(
                            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)
                        ),
                    }
                )
    except PermissionError:
        report["locks"] = [
            {"warning": f"Cannot read lock directory (permission denied): {lock_dir}"}
        ]

    # Active and needs_operator jobs.
    try:
        for state_key, field in [
            ("running", "active_jobs"),
            ("needs_operator", "needs_operator_jobs"),
        ]:
            jobs = db.list_jobs(config, state=state_key, limit=20)
            report[field] = jobs
        if report["needs_operator_jobs"]:
            count = len(report["needs_operator_jobs"])
            report["warnings"].append(
                f"{count} job(s) in 'needs_operator' state require manual reconciliation."
            )

        # Queued write_archive jobs (ready to run once tape is mounted).
        wa_jobs = [
            j
            for j in db.list_jobs(config, limit=100)
            if j["type"] == "write_archive"
            and j["state"] in ("queued", "waiting_for_mount")
        ]
        report["queued_write_archive_jobs"] = wa_jobs
        if wa_jobs:
            report["warnings"].append(
                f"{len(wa_jobs)} write_archive job(s) are queued. "
                "Mount the target tape(s) and run 'tapelib write-archive --job-id <id>'."
            )
    except Exception as exc:
        report["warnings"].append(f"Could not read jobs: {exc}")

    # Cache space.
    cache_path = Path(
        config.get("cache", {}).get("path", "/run/media/ash/cache/tapelib")
    )
    if cache_path.exists():
        try:
            sv = os.statvfs(cache_path)
            report["cache"] = {
                "path": str(cache_path),
                "free_bytes": sv.f_frsize * sv.f_bavail,
                "total_bytes": sv.f_frsize * sv.f_blocks,
            }
        except OSError as exc:
            report["cache"] = {"path": str(cache_path), "error": str(exc)}
    else:
        report["cache"] = {
            "path": str(cache_path),
            "warning": "Cache path does not exist.",
        }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _command_cleanup_cache(args: argparse.Namespace) -> int:
    from . import archive as _archive

    config = _load_config(Path(args.config))
    payload = _archive.cleanup_cache(config)
    _write_json(_state_dir(config) / "status" / "cache-cleanup.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _verify_targets(config: dict[str, Any], target: str | None) -> list[tuple[str, str, str | None]]:
    if target:
        return [_resolve_tape_target(config, target, require_mounted=True)]

    allowed_generations = set(
        config.get("library", {}).get("allowedGenerations", ["L5"])
    )
    tape_by_id = {
        tape["id"]: tape
        for tape in db.list_tapes(config, include_ignored=True)
        if tape.get("id") is not None
    }
    targets: list[tuple[str, str, str | None]] = []

    for drive in db.list_drives(config):
        loaded_tape_id = drive.get("loaded_tape_id")
        if loaded_tape_id is None:
            continue
        tape = tape_by_id.get(loaded_tape_id)
        if tape is None:
            continue
        generation = tape.get("generation") or hardware.barcode_generation(
            tape["barcode"]
        )
        if allowed_generations and generation not in allowed_generations:
            continue
        mount_path = drive.get("mount_path")
        if not mount_path or not _is_mounted(mount_path):
            continue
        targets.append((tape["barcode"], mount_path, drive["id"]))

    if targets:
        return targets

    raise executor.ExecutionError(
        "No mounted allowed tape is available to verify. "
        "Pass --tape <barcode|drive> or mount an LTFS tape first."
    )


def _verify_payload(
    config: dict[str, Any], *, target: str | None, mode: str
) -> dict[str, Any]:
    targets = _verify_targets(config, target)
    checked = 0
    verified = 0
    missing = 0
    checksum_mismatches = 0
    results: list[dict[str, Any]] = []
    tapes: list[dict[str, Any]] = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    with closing(db.connect(config)) as connection:
        with connection:
            for barcode, mount_path, drive_id in targets:
                tape_checked = 0
                tape_verified = 0
                tape_missing = 0
                tape_checksum_mismatches = 0
                tape_results: list[dict[str, Any]] = []

                files = connection.execute(
                    """
                    SELECT files.*, tapes.barcode AS tape_barcode
                    FROM files
                    JOIN tapes ON tapes.id = files.tape_id
                    WHERE tapes.barcode = ? AND files.is_dir = 0
                    ORDER BY files.path
                    """,
                    (barcode,),
                ).fetchall()

                for row in files:
                    checked += 1
                    tape_checked += 1
                    tape_path = Path(mount_path) / row["path"]
                    entry = {
                        "path": row["path"],
                        "state": "verified",
                        "tape_barcode": barcode,
                    }
                    if not tape_path.is_file():
                        missing += 1
                        tape_missing += 1
                        entry["state"] = "read_error"
                        entry["error"] = "missing_on_tape"
                        connection.execute(
                            "UPDATE files SET state = 'read_error' WHERE id = ?",
                            (row["id"],),
                        )
                        tape_results.append(entry)
                        results.append(entry)
                        continue

                    if mode == "checksums" and row["checksum_sha256"]:
                        actual_checksum = _checksum_sha256(tape_path)
                        entry["actual_checksum_sha256"] = actual_checksum
                        if actual_checksum != row["checksum_sha256"]:
                            checksum_mismatches += 1
                            tape_checksum_mismatches += 1
                            entry["state"] = "read_error"
                            entry["error"] = "checksum_mismatch"
                            connection.execute(
                                "UPDATE files SET state = 'read_error' WHERE id = ?",
                                (row["id"],),
                            )
                            tape_results.append(entry)
                            results.append(entry)
                            continue

                    verified += 1
                    tape_verified += 1
                    connection.execute(
                        "UPDATE files SET state = 'verified', verified_at = ? WHERE id = ?",
                        (now, row["id"]),
                    )
                    tape_results.append(entry)
                    results.append(entry)

                connection.execute(
                    "UPDATE tapes SET last_verified_at = ? WHERE barcode = ?",
                    (now, barcode),
                )
                tapes.append(
                    {
                        "tape_barcode": barcode,
                        "drive": drive_id,
                        "mount_path": mount_path,
                        "checked_files": tape_checked,
                        "verified_files": tape_verified,
                        "missing_files": tape_missing,
                        "checksum_mismatches": tape_checksum_mismatches,
                        "results": tape_results,
                    }
                )

    payload = {
        "generated_at": now,
        "mode": mode,
        "checked_files": checked,
        "verified_files": verified,
        "missing_files": missing,
        "checksum_mismatches": checksum_mismatches,
        "tapes": tapes,
        "results": results,
    }
    if len(tapes) == 1:
        payload["tape_barcode"] = tapes[0]["tape_barcode"]
        payload["mount_path"] = tapes[0]["mount_path"]
    _write_json(_state_dir(config) / "status" / "verify.json", payload)
    return payload


def _command_verify(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    payload = _verify_payload(
        config,
        target=getattr(args, "tape", None),
        mode=args.mode,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _command_import_inventory(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    target = Path(args.source)
    source_barcode: str | None = None

    if target.exists():
        if target.is_dir():
            target = target / "TAPELIB-INVENTORY.json"
    else:
        source_barcode, mount_path, _drive_id = _resolve_tape_target(
            config,
            args.source,
            require_mounted=True,
        )
        target = Path(mount_path) / "TAPELIB-INVENTORY.json"

    if not target.is_file():
        raise executor.ExecutionError(
            f"Inventory manifest not found: {target}"
        )

    try:
        manifest = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise executor.ExecutionError(
            f"Inventory manifest is not valid JSON: {exc}"
        ) from exc

    payload = db.import_inventory_manifest(
        config,
        manifest,
        source_barcode=source_barcode,
        source_path=str(target),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _resolve_tape_target(
    config: dict[str, Any],
    target: str,
    *,
    require_mounted: bool = False,
) -> tuple[str, str, str | None]:
    drives_cfg = config.get("library", {}).get("drives", [])
    resolved_barcode: str | None = None
    resolved_mount: str | None = None
    resolved_drive: str | None = None

    for drive_cfg in drives_cfg:
        if drive_cfg["name"] != target:
            continue
        drive_record = db.get_drive(config, drive_cfg["name"])
        if drive_record is None or drive_record.get("loaded_tape_id") is None:
            raise executor.ExecutionError(
                f"Drive {target!r} has no loaded tape according to the catalog. "
                "Run 'tapelib inventory' first to refresh drive state."
            )
        tape_by_id = {
            t["id"]: t["barcode"]
            for t in db.list_tapes(config, include_ignored=True)
            if t.get("id") is not None
        }
        resolved_barcode = tape_by_id.get(drive_record["loaded_tape_id"])
        if resolved_barcode is None:
            raise executor.ExecutionError(
                f"Drive {target!r} has no recognized loaded tape barcode."
            )
        resolved_mount = drive_cfg.get("mountPath")
        resolved_drive = drive_cfg["name"]
        break

    if resolved_barcode is None:
        resolved_barcode = target
        tape_by_id = {
            t["id"]: t["barcode"]
            for t in db.list_tapes(config, include_ignored=True)
            if t.get("id") is not None
        }
        for drive_rec in db.list_drives(config):
            if tape_by_id.get(drive_rec.get("loaded_tape_id")) == resolved_barcode:
                resolved_drive = drive_rec["id"]
                for drive_cfg in drives_cfg:
                    if drive_cfg["name"] == drive_rec["id"]:
                        resolved_mount = drive_cfg.get("mountPath")
                        break
                break

    if resolved_mount is None:
        raise executor.ExecutionError(
            f"Tape {resolved_barcode!r} is not loaded in any configured drive. "
            "Load and mount it first."
        )
    if require_mounted and not _is_mounted(resolved_mount):
        raise executor.ExecutionError(
            f"Tape {resolved_barcode!r} is loaded in a drive but LTFS is not "
            f"mounted at {resolved_mount}. Run 'tapelib mount-ltfs <drive>' first."
        )

    return resolved_barcode, resolved_mount, resolved_drive


def _command_daemon(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    database = db.initialize_database(config)
    interrupted_jobs = db.reconcile_interrupted_jobs(config)
    running = True
    scheduler_cfg = config.get("scheduler", {})
    auto_retrieve = bool(scheduler_cfg.get("automaticRetrieve", False))
    poll_seconds = int(scheduler_cfg.get("pollSeconds", 5))
    last_scheduler_result: dict[str, Any] | None = None

    def _stop(_signum: int, _frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        if auto_retrieve:
            last_scheduler_result = _run_queue_once(config, auto=True)
            database = db.initialize_database(config)
        payload = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "database": database,
            "interrupted_jobs_reconciled": interrupted_jobs,
            "pid": os.getpid(),
            "scheduler": {
                "automatic_retrieve": auto_retrieve,
                "last_result": last_scheduler_result,
                "poll_seconds": poll_seconds,
            },
            "status": "running",
            "library": _readable_inventory(config),
        }
        _write_json(_status_path(config), payload)
        time.sleep(poll_seconds)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "database": database,
        "pid": os.getpid(),
        "status": "stopped",
        "library": _readable_inventory(config),
    }
    _write_json(_status_path(config), payload)
    return 0


def _command_mount_fuse(args: argparse.Namespace) -> int:
    from . import fuse_fs

    config = _load_config(Path(args.config))
    mount_point = args.mount_point or config.get("fuse", {}).get(
        "mountPoint", "/mnt/tapelib"
    )
    fuse_fs.mount(
        config,
        mount_point,
        foreground=args.foreground,
        allow_other=args.allow_other,
    )
    return 0


class _TapelibHandler(BaseHTTPRequestHandler):
    config: dict[str, Any] = {}

    def _send_json(self, payload: dict[str, Any], status_code: int = 200) -> None:
        body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, body: str, status_code: int = 200) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            self._send_html(_operator_console_html())
            return
        if parsed.path == "/healthz":
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/console":
            self._send_json(_operator_console_payload(self.config))
            return
        if parsed.path == "/api/status":
            self._send_json(_status_payload(self.config))
            return
        if parsed.path == "/api/inventory":
            self._send_json(_inventory_payload(self.config))
            return
        if parsed.path == "/api/tapes":
            self._send_json({"tapes": db.list_tapes(self.config, include_ignored=True)})
            return
        if parsed.path == "/api/drives":
            self._send_json({"drives": db.list_drives(self.config)})
            return
        if parsed.path == "/api/files":
            tape = query.get("tape", [None])[0]
            limit = int(query.get("limit", ["500"])[0])
            self._send_json(_files_payload(self.config, tape_barcode=tape, limit=limit))
            return
        if parsed.path == "/api/cache":
            self._send_json(_cache_payload(self.config))
            return
        if parsed.path == "/api/warnings":
            self._send_json(_warnings_payload(self.config))
            return
        if parsed.path == "/api/jobs":
            state = query.get("state", [None])[0]
            limit = int(query.get("limit", ["50"])[0])
            self._send_json(
                {"jobs": db.list_jobs(self.config, state=state, limit=limit)}
            )
            return
        if parsed.path == "/api/journal":
            job_id = query.get("job_id", [None])[0]
            limit = int(query.get("limit", ["100"])[0])
            self._send_json(
                {"events": db.list_job_events(self.config, job_id=job_id, limit=limit)}
            )
            return
        if parsed.path == "/api/plan/games":
            try:
                self._send_json(_plan_game_backup(self.config))
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status_code=400)
            return
        self._send_json({"error": "not_found"}, status_code=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/actions/"):
            self._send_json({"error": "not_found"}, status_code=404)
            return
        action = parsed.path.removeprefix("/api/actions/")
        try:
            payload = self._read_json_body()
            self._send_json(_web_action(self.config, action, payload))
        except executor.ExecutionError as exc:
            self._send_json({"error": str(exc)}, status_code=400)
        except KeyError as exc:
            self._send_json({"error": f"Unknown job id: {exc}"}, status_code=404)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise executor.ExecutionError(f"Request body is not valid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise executor.ExecutionError("Request body must be a JSON object.")
        return payload

    def log_message(self, format: str, *args: Any) -> None:
        return


def _command_serve_web(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    webui = config.get("webui", {})
    host = webui.get("host", "127.0.0.1")
    port = int(webui.get("port", 5001))

    handler = type("TapelibHandler", (_TapelibHandler,), {"config": config})
    server = ThreadingHTTPServer((host, port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


def _operator_console_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>tapelib</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { margin: 0; background: Canvas; color: CanvasText; }
    header { padding: 16px 20px; border-bottom: 1px solid color-mix(in srgb, CanvasText 18%, transparent); }
    main { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); padding: 16px; }
    section { border: 1px solid color-mix(in srgb, CanvasText 18%, transparent); border-radius: 6px; padding: 12px; min-width: 0; }
    h1 { font-size: 20px; margin: 0; }
    h2 { font-size: 15px; margin: 0 0 10px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    td, th { border-top: 1px solid color-mix(in srgb, CanvasText 12%, transparent); padding: 6px; text-align: left; vertical-align: top; }
    code, pre { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
    pre { overflow: auto; margin: 0; white-space: pre-wrap; }
    .muted { opacity: .7; }
  </style>
</head>
<body>
  <header><h1>tapelib</h1><div id="updated" class="muted"></div></header>
  <main>
    <section><h2>Warnings</h2><div id="warnings"></div></section>
    <section><h2>Drives</h2><div id="drives"></div></section>
    <section><h2>Tapes</h2><div id="tapes"></div></section>
    <section><h2>Jobs</h2><div id="jobs"></div></section>
    <section><h2>Cache</h2><pre id="cache"></pre></section>
  </main>
  <script>
    const text = value => value === null || value === undefined ? "" : String(value);
    function table(rows, columns) {
      if (!rows.length) return '<div class="muted">None</div>';
      const head = '<tr>' + columns.map(c => `<th>${c}</th>`).join('') + '</tr>';
      const body = rows.map(row => '<tr>' + columns.map(c => `<td>${text(row[c])}</td>`).join('') + '</tr>').join('');
      return `<table>${head}${body}</table>`;
    }
    async function refresh() {
      const payload = await fetch('/api/console').then(r => r.json());
      document.getElementById('updated').textContent = new Date().toLocaleString();
      document.getElementById('warnings').innerHTML = table(payload.warnings.warnings, ['severity', 'kind', 'message']);
      document.getElementById('drives').innerHTML = table(payload.drives, ['id', 'state', 'mount_path']);
      document.getElementById('tapes').innerHTML = table(payload.tapes, ['barcode', 'state', 'current_location']);
      document.getElementById('jobs').innerHTML = table(payload.jobs, ['id', 'type', 'state']);
      document.getElementById('cache').textContent = JSON.stringify(payload.cache, null, 2);
    }
    refresh();
    setInterval(refresh, 10000);
  </script>
</body>
</html>
"""


def _build_parser() -> argparse.ArgumentParser:
    def add_config_arg(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--config",
            default=argparse.SUPPRESS,
            help="Path to tapelib JSON config",
        )

    parser = argparse.ArgumentParser(
        description="tapelib tape library overlay scaffold"
    )
    add_config_arg(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_db = subparsers.add_parser(
        "init-db", help="Create or migrate the persistent SQLite catalog and journal"
    )
    add_config_arg(init_db)
    init_db.set_defaults(func=_command_init_db)

    backup_db = subparsers.add_parser(
        "backup-db", help="Create an online SQLite catalog backup"
    )
    add_config_arg(backup_db)
    backup_db.add_argument(
        "--output-dir",
        help="Backup directory. Defaults to database.backupDir or <stateDir>/backups.",
    )
    backup_db.set_defaults(func=_command_backup_db)

    inventory = subparsers.add_parser("inventory", help="Print configured inventory")
    add_config_arg(inventory)
    inventory.add_argument(
        "--json",
        action="store_true",
        help="Accepted for compatibility; output is always JSON",
    )
    inventory.add_argument(
        "--write-status",
        action="store_true",
        help="Write inventory status into the state dir",
    )
    inventory.set_defaults(func=_command_inventory)

    status = subparsers.add_parser("status", help="Print runtime status")
    add_config_arg(status)
    status.set_defaults(func=_command_status)

    filesystem_smoke = subparsers.add_parser(
        "filesystem-smoke-test",
        help="Time side-effect-free tapelib FUSE filesystem operations",
    )
    add_config_arg(filesystem_smoke)
    filesystem_smoke.add_argument(
        "--mount-point",
        help="Mounted tapelib FUSE path. Defaults to services.tapelib.fuse.mountPoint.",
    )
    filesystem_smoke.add_argument(
        "--include-hardware",
        action="store_true",
        help="Also read hardware-observation files such as system/inventory.json.",
    )
    filesystem_smoke.add_argument(
        "--fast-budget-ms",
        type=float,
        default=FILESYSTEM_FAST_BUDGET_MS,
        help="Maximum expected duration for virtual-only operations.",
    )
    filesystem_smoke.add_argument(
        "--fail-slow",
        action="store_true",
        help="Exit nonzero if any operation exceeds its budget or fails.",
    )
    filesystem_smoke.add_argument(
        "--json", action="store_true", help="Print the report as JSON."
    )
    filesystem_smoke.set_defaults(func=_command_filesystem_smoke_test)

    create_job = subparsers.add_parser(
        "create-job", help="Persist a new queued job shell"
    )
    add_config_arg(create_job)
    create_job.add_argument(
        "job_type", help="Job type, for example inventory_library or write_set_to_tape"
    )
    create_job.add_argument("--priority", type=int, default=100)
    create_job.add_argument("--source-json", help="JSON source payload")
    create_job.add_argument("--target-json", help="JSON target payload")
    create_job.add_argument("--required-bytes", type=int)
    create_job.add_argument("--assigned-drive")
    create_job.add_argument("--assigned-tape-id", type=int)
    create_job.set_defaults(func=_command_create_job)

    retrieve = subparsers.add_parser(
        "retrieve",
        help="Queue a bulk copy-out of cataloged files to a local destination",
    )
    add_config_arg(retrieve)
    retrieve.add_argument(
        "--manifest",
        required=True,
        help="JSON list, or object with files, containing tape:path entries",
    )
    retrieve.add_argument(
        "--dest",
        required=True,
        help="Local destination root. Files preserve tape/archive paths below it.",
    )
    retrieve.add_argument("--priority", type=int, default=100)
    retrieve.set_defaults(func=_command_retrieve)

    cancel = subparsers.add_parser(
        "cancel", help="Cancel a queued or waiting job before active hardware work"
    )
    add_config_arg(cancel)
    cancel.add_argument("job_id")
    cancel.set_defaults(func=_command_cancel)

    run_queue = subparsers.add_parser(
        "run-queue", help="Run one safe queued job explicitly"
    )
    add_config_arg(run_queue)
    run_queue.add_argument(
        "--once",
        action="store_true",
        help="Run at most one queued job. Required for this scaffold.",
    )
    run_queue.add_argument(
        "--auto",
        action="store_true",
        help="Allow retrieve jobs to load, mount, copy, and release tapes automatically.",
    )
    run_queue.add_argument("--job-id", help="Run only the selected job id")
    run_queue.set_defaults(func=_command_run_queue)

    jobs = subparsers.add_parser("jobs", help="List persisted jobs")
    add_config_arg(jobs)
    jobs.add_argument("--state", help="Filter by job state")
    jobs.add_argument("--limit", type=int, default=50)
    jobs.set_defaults(func=_command_jobs)

    job_status_parser = subparsers.add_parser(
        "job-status", help="Print a progress-oriented JSON snapshot for one job"
    )
    add_config_arg(job_status_parser)
    job_status_parser.add_argument("job_id")
    job_status_parser.add_argument("--event-limit", type=int, default=50)
    job_status_parser.set_defaults(func=_command_job_status)

    journal = subparsers.add_parser("journal", help="List persisted job journal events")
    add_config_arg(journal)
    journal.add_argument("--job-id", help="Filter events by job id")
    journal.add_argument("--limit", type=int, default=100)
    journal.set_defaults(func=_command_journal)

    load_tape = subparsers.add_parser(
        "load-tape", help="Load an allowed tape barcode into a configured drive"
    )
    add_config_arg(load_tape)
    load_tape.add_argument("barcode")
    load_tape.add_argument("drive")
    load_tape.set_defaults(func=_command_load_tape)

    unload_tape = subparsers.add_parser(
        "unload-tape", help="Unload a configured drive back to its source slot"
    )
    add_config_arg(unload_tape)
    unload_tape.add_argument("drive")
    unload_tape.add_argument("--slot", type=int, help="Destination storage slot")
    unload_tape.set_defaults(func=_command_unload_tape)

    mount_ltfs = subparsers.add_parser(
        "mount-ltfs", help="Mount the loaded LTFS tape for a configured drive"
    )
    add_config_arg(mount_ltfs)
    mount_ltfs.add_argument("drive")
    mount_ltfs.add_argument(
        "--read-write",
        action="store_true",
        help="Mount read-write. Default is read-only.",
    )
    mount_ltfs.set_defaults(func=_command_mount_ltfs)

    unmount_ltfs = subparsers.add_parser(
        "unmount-ltfs", help="Unmount the LTFS mount for a configured drive"
    )
    add_config_arg(unmount_ltfs)
    unmount_ltfs.add_argument("drive")
    unmount_ltfs.set_defaults(func=_command_unmount_ltfs)

    reconcile_hardware = subparsers.add_parser(
        "reconcile-hardware",
        help="Reconcile active hardware jobs against current changer and mount state",
    )
    add_config_arg(reconcile_hardware)
    reconcile_hardware.set_defaults(func=_command_reconcile_hardware)

    inventory_manifest = subparsers.add_parser(
        "inventory-manifest",
        help="Render an additive library inventory manifest for writing to LTFS tapes",
    )
    add_config_arg(inventory_manifest)
    inventory_manifest.add_argument(
        "--output",
        help="Optional path to write, for example /var/lib/tapelib/status/TAPELIB-INVENTORY.json",
    )
    inventory_manifest.set_defaults(func=_command_inventory_manifest)

    import_inventory = subparsers.add_parser(
        "import-inventory",
        help="Import TAPELIB-INVENTORY.json from a mounted tape, mount path, or JSON file",
    )
    add_config_arg(import_inventory)
    import_inventory.add_argument(
        "source",
        help="Drive name, loaded tape barcode, mount path, or manifest JSON file path",
    )
    import_inventory.set_defaults(func=_command_import_inventory)

    plan_games = subparsers.add_parser(
        "plan-games-backup", help="Build a multi-tape plan for the games archive roots"
    )
    add_config_arg(plan_games)
    plan_games.add_argument(
        "--write-status", action="store_true", help="Write the plan into the state dir"
    )
    plan_games.set_defaults(func=_command_plan_games_backup)

    games_status = subparsers.add_parser(
        "games-backup-status",
        help="Print a human-readable game-library backup progress report",
    )
    add_config_arg(games_status)
    games_status.add_argument(
        "--json", action="store_true", help="Print the progress report as JSON"
    )
    games_status.add_argument(
        "--plan",
        action="store_true",
        help="Include a fresh source scan and full current plan. This can be slow.",
    )
    games_status.add_argument(
        "--no-plan",
        action="store_true",
        help="Do not include the fresh source scan. This is the default.",
    )
    games_status.set_defaults(func=_command_games_backup_status)

    index_tape = subparsers.add_parser(
        "index-tape",
        help="Walk a mounted LTFS tape and update the file catalog",
    )
    add_config_arg(index_tape)
    index_tape.add_argument(
        "barcode_or_drive",
        help="Tape barcode (e.g. 385182L5) or configured drive name (e.g. drive0)",
    )
    index_tape.set_defaults(func=_command_index_tape)

    stage_games = subparsers.add_parser(
        "stage-games-backup",
        help=(
            "Stage game archive files to the local cache and queue write_archive jobs. "
            "Uses the configured games.sourceRoots and games.selectedTapes."
        ),
    )
    add_config_arg(stage_games)
    stage_games.add_argument(
        "--plan-file",
        help="Path to a JSON plan file from 'plan-games-backup --write-status'. "
        "If omitted, a fresh plan is generated.",
    )
    stage_games.add_argument(
        "--tape",
        metavar="BARCODE",
        help="Only stage files assigned to this tape barcode. "
        "Use this to stage one tape at a time when cache space is limited.",
    )
    stage_games.add_argument(
        "--max-staged-bytes",
        metavar="SIZE",
        help="Optional staging budget for this run, such as 500G. Defaults to the currently available cache budget.",
    )
    stage_games.set_defaults(func=_command_stage_games_backup)

    write_archive = subparsers.add_parser(
        "write-archive",
        help=(
            "Write a staged write_archive job to the loaded and mounted LTFS tape. "
            "The target tape must be mounted read-write before running this command."
        ),
    )
    add_config_arg(write_archive)
    write_archive.add_argument("--job-id", required=True, help="write_archive job UUID")
    write_archive.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Allow retrying a failed or needs_operator write_archive job. "
            "Already written files are detected by checksum and skipped safely."
        ),
    )
    write_archive.set_defaults(func=_command_write_archive)

    run_games = subparsers.add_parser(
        "games-backup-run-next",
        help="Run the oldest runnable staged game-library write_archive job",
    )
    add_config_arg(run_games)
    run_games.add_argument(
        "--resume",
        action="store_true",
        help="Allow failed/needs-operator game write jobs to be resumed.",
    )
    run_games.add_argument(
        "--json", action="store_true", help="Print the completed job as JSON"
    )
    run_games.set_defaults(func=_command_games_backup_run_next)

    promote_ingest = subparsers.add_parser(
        "promote-ingest",
        help="Promote a queued cached FUSE ingest job into a write_archive job for an explicit target tape",
    )
    add_config_arg(promote_ingest)
    promote_ingest.add_argument("--job-id", required=True, help="ingest_cached_files job UUID")
    promote_ingest.add_argument("--tape", required=True, help="Target tape barcode")
    promote_ingest.add_argument(
        "--namespace",
        help="Archive namespace prefix. Defaults to the ingest job target or games.namespacePrefix.",
    )
    promote_ingest.set_defaults(func=_command_promote_ingest)

    doctor = subparsers.add_parser(
        "doctor",
        help="Print a diagnostic report: drives, mounts, locks, active jobs, cache usage",
    )
    add_config_arg(doctor)
    doctor.set_defaults(func=_command_doctor)

    cleanup_cache = subparsers.add_parser(
        "cleanup-cache", help="Run the cache cleanup scaffold"
    )
    add_config_arg(cleanup_cache)
    cleanup_cache.set_defaults(func=_command_cleanup_cache)

    verify = subparsers.add_parser(
        "verify",
        help="Verify cataloged files on a mounted LTFS tape by existence or checksum",
    )
    add_config_arg(verify)
    verify.add_argument(
        "--tape",
        help="Tape barcode or configured drive name for the mounted LTFS tape",
    )
    verify.add_argument(
        "--mode",
        choices=["metadata", "checksums"],
        default="metadata",
        help="Verification mode. 'metadata' checks existence; 'checksums' also hashes files with known checksums.",
    )
    verify.set_defaults(func=_command_verify)

    daemon = subparsers.add_parser("daemon", help="Run the lightweight state daemon")
    add_config_arg(daemon)
    daemon.set_defaults(func=_command_daemon)

    mount_fuse = subparsers.add_parser(
        "mount-fuse", help="Mount the read-only browse/status FUSE overlay"
    )
    add_config_arg(mount_fuse)
    mount_fuse.add_argument(
        "--mount-point",
        help="Mount point. Defaults to services.tapelib.fuse.mountPoint.",
    )
    mount_fuse.add_argument(
        "--foreground",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run the FUSE process in the foreground.",
    )
    mount_fuse.add_argument(
        "--allow-other",
        action="store_true",
        help="Allow users other than the service user to browse the mount.",
    )
    mount_fuse.set_defaults(func=_command_mount_fuse)

    serve_web = subparsers.add_parser(
        "serve-web", help="Run the lightweight JSON web service"
    )
    add_config_arg(serve_web)
    serve_web.set_defaults(func=_command_serve_web)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "config"):
        args.config = str(_default_config_path())
    try:
        return args.func(args)
    except executor.ExecutionError as exc:
        print(
            json.dumps({"error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr
        )
        return 1
