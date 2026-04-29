from __future__ import annotations

import argparse
import json
import os
import posixpath
import shutil
import signal
import subprocess
import sys
import time
import uuid
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


def _default_config_path() -> Path:
    return Path(os.environ.get("TAPELIB_CONFIG_PATH", "/etc/tapelib/config.json"))


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


def _command_status(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    print(json.dumps(_status_payload(config), indent=2, sort_keys=True))
    return 0


def _command_init_db(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    print(json.dumps(db.initialize_database(config), indent=2, sort_keys=True))
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
            }
        )

    requested_files.sort(
        key=lambda file: (file["tape_barcode"], file["archive_path"])
    )
    groups = _retrieve_groups(config, requested_files)
    return {
        "manifest_path": str(manifest_path),
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
    result = _run_queue_once(config, job_id=args.job_id)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _run_queue_once(config: dict[str, Any], *, job_id: str | None = None) -> dict[str, Any]:
    try:
        job = _next_retrieve_job(config, job_id=job_id)
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
    if job["state"] not in RUNNABLE_RETRIEVE_STATES:
        raise executor.ExecutionError(
            f"Job {job['id']} is {job['state']} and is not runnable by mounted-only retrieve."
        )

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
    config: dict[str, Any], *, job_id: str | None = None
) -> dict[str, Any] | None:
    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        if job_id is not None:
            return db.get_job(connection, job_id)
        placeholders = ", ".join("?" for _ in RUNNABLE_RETRIEVE_STATES)
        row = connection.execute(
            f"""
            SELECT * FROM jobs
            WHERE type = ?
              AND state IN ({placeholders})
            ORDER BY priority, created_at
            LIMIT 1
            """,
            (RETRIEVE_JOB_TYPE, *RUNNABLE_RETRIEVE_STATES),
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


def _is_mounted(path: str) -> bool:
    completed = subprocess.run(
        ["findmnt", "-n", "--target", path],
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def _run_mounted_retrieve_job(
    config: dict[str, Any], job: dict[str, Any], mount_map: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    copied_files: list[dict[str, Any]] = []
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

    for entry in copy_plan:
        with closing(db.connect(config)) as connection:
            with connection:
                db.append_job_event(
                    connection,
                    job["id"],
                    "retrieve_file_started",
                    "Started copying a file from mounted LTFS.",
                    {
                        "tape_barcode": entry["tape_barcode"],
                        "archive_path": entry["archive_path"],
                        "source_path": str(entry["source_path"]),
                        "destination_path": str(entry["destination_path"]),
                    },
                )

        _copy_retrieve_file(entry["source_path"], entry["destination_path"])
        copied_file = {
            "tape_barcode": entry["tape_barcode"],
            "archive_path": entry["archive_path"],
            "source_path": str(entry["source_path"]),
            "destination_path": str(entry["destination_path"]),
            "size_bytes": entry["size_bytes"],
        }
        copied_files.append(copied_file)

        with closing(db.connect(config)) as connection:
            with connection:
                db.append_job_event(
                    connection,
                    job["id"],
                    "retrieve_file_complete",
                    "Completed copying a file from mounted LTFS.",
                    copied_file,
                )

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
                }
            )
    return copy_plan


def _preflight_copy_plan(copy_plan: list[dict[str, Any]]) -> None:
    for entry in copy_plan:
        source_path = entry["source_path"]
        destination_path = entry["destination_path"]
        if destination_path.exists():
            raise executor.ExecutionError(
                f"Destination already exists and will not be overwritten: {destination_path}"
            )
        if not source_path.is_file():
            raise executor.ExecutionError(f"Mounted source file is missing: {source_path}")


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


def _plan_game_backup(config: dict[str, Any]) -> dict[str, Any]:
    games = config.get("games", {})
    tape_names = games.get("selectedTapes", [])
    tape_capacity_bytes = int(games.get("tapeCapacityBytes", 0))
    units = _scan_game_units(config)

    if tape_capacity_bytes <= 0:
        raise ValueError("games.tapeCapacityBytes must be set to a positive integer.")
    if tape_names == []:
        raise ValueError(
            "games.selectedTapes must contain at least one tape barcode for planning."
        )

    assignments: list[dict[str, Any]] = []
    current_tape_index = 0
    current_remaining_bytes = tape_capacity_bytes

    for unit in units:
        unit_size = unit.size_bytes
        if unit_size <= current_remaining_bytes:
            assignments.append(
                {
                    "tape": tape_names[current_tape_index],
                    "unit_path": unit.unit_path,
                    "size_bytes": unit_size,
                    "split": {
                        "enabled": False,
                        "part": 1,
                    },
                    "files": [asdict(file) for file in unit.files],
                }
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
                {
                    "tape": tape_names[current_tape_index],
                    "unit_path": unit.unit_path,
                    "size_bytes": unit_size,
                    "split": {
                        "enabled": False,
                        "part": 1,
                    },
                    "files": [asdict(file) for file in unit.files],
                }
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

    per_tape: dict[str, dict[str, Any]] = {}
    for assignment in assignments:
        tape_summary = per_tape.setdefault(
            assignment["tape"],
            {
                "tape": assignment["tape"],
                "units": [],
                "size_bytes": 0,
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
        "selected_tapes": tape_names,
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


def _command_cleanup_cache(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cache": config.get("cache", {}),
        "status": "planned-only",
    }
    _write_json(_state_dir(config) / "status" / "cache-cleanup.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _command_verify(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "planned-only",
        "library": _readable_inventory(config),
    }
    _write_json(_state_dir(config) / "status" / "verify.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _command_daemon(args: argparse.Namespace) -> int:
    config = _load_config(Path(args.config))
    database = db.initialize_database(config)
    interrupted_jobs = db.reconcile_interrupted_jobs(config)
    running = True

    def _stop(_signum: int, _frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while running:
        payload = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "database": database,
            "interrupted_jobs_reconciled": interrupted_jobs,
            "pid": os.getpid(),
            "status": "running",
            "library": _readable_inventory(config),
        }
        _write_json(_status_path(config), payload)
        time.sleep(5)

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

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/healthz":
            self._send_json({"ok": True})
            return
        if parsed.path == "/api/status":
            self._send_json(_status_payload(self.config))
            return
        if parsed.path == "/api/inventory":
            self._send_json(_inventory_payload(self.config))
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

    plan_games = subparsers.add_parser(
        "plan-games-backup", help="Build a multi-tape plan for the games archive roots"
    )
    add_config_arg(plan_games)
    plan_games.add_argument(
        "--write-status", action="store_true", help="Write the plan into the state dir"
    )
    plan_games.set_defaults(func=_command_plan_games_backup)

    cleanup_cache = subparsers.add_parser(
        "cleanup-cache", help="Run the cache cleanup scaffold"
    )
    add_config_arg(cleanup_cache)
    cleanup_cache.set_defaults(func=_command_cleanup_cache)

    verify = subparsers.add_parser("verify", help="Run the verification scaffold")
    add_config_arg(verify)
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
