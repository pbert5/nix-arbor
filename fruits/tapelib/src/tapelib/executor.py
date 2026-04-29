from __future__ import annotations

import fcntl
import subprocess
from contextlib import contextmanager, closing
from pathlib import Path
from typing import Any

from . import db, hardware


class ExecutionError(RuntimeError):
    pass


def load_tape(config: dict[str, Any], barcode: str, drive_name: str) -> dict[str, Any]:
    allowed_generations = config.get("library", {}).get("allowedGenerations", ["L5"])
    _require_allowed_barcode(barcode, allowed_generations)
    inventory = _refresh_inventory(config)
    slot = _slot_for_barcode(inventory, barcode)
    if slot is None:
        raise ExecutionError(f"Tape {barcode} is not present in a storage slot.")
    drive_index, drive = _configured_drive(config, drive_name)
    _require_drive_empty(inventory, drive_index)

    tape = db.get_tape(config, barcode)
    tape_id = None if tape is None else tape["id"]
    source = {"barcode": barcode, "slot": slot["slot"]}
    target = {"drive": drive_name, "drive_index": drive_index}
    job = _create_job(
        config,
        "load_tape",
        source=source,
        target=target,
        assigned_drive=drive_name,
        assigned_tape_id=tape_id,
    )

    try:
        with _lock(config, "changer"):
            with closing(db.connect(config)) as connection:
                with connection:
                    db.transition_job(
                        connection,
                        job["id"],
                        "waiting_for_changer",
                        event_type="lock_acquired",
                        message="Changer lock acquired for tape load.",
                        data={"barcode": barcode, "drive": drive_name},
                    )
                    db.transition_job(
                        connection,
                        job["id"],
                        "loading_tape",
                        event_type="before_mtx_load",
                        message="About to load tape into drive.",
                        data={
                            "command": [
                                "mtx",
                                "-f",
                                _changer(config),
                                "load",
                                str(slot["slot"]),
                                str(drive_index),
                            ]
                        },
                    )

            _run(
                [
                    "mtx",
                    "-f",
                    _changer(config),
                    "load",
                    str(slot["slot"]),
                    str(drive_index),
                ]
            )

        database = _refresh_inventory(config)
        _complete_job(config, job["id"], "Tape loaded.", database)
        return _job(config, job["id"])
    except ExecutionError as exc:
        _fail_job(config, job["id"], str(exc))
        raise


def unload_tape(
    config: dict[str, Any],
    drive_name: str,
    *,
    destination_slot: int | None = None,
) -> dict[str, Any]:
    inventory = _refresh_inventory(config)
    drive_index, _drive = _configured_drive(config, drive_name)
    drive_status = _drive_status(inventory, drive_index)
    if drive_status is None or drive_status.get("state") != "full":
        raise ExecutionError(f"Drive {drive_name} is not loaded.")
    slot = destination_slot or drive_status.get("source_slot")
    if slot is None:
        raise ExecutionError("No destination slot is known; pass --slot explicitly.")

    barcode = drive_status.get("barcode")
    tape = None if barcode is None else db.get_tape(config, barcode)
    job = _create_job(
        config,
        "unload_tape",
        source={"drive": drive_name, "drive_index": drive_index, "barcode": barcode},
        target={"slot": slot},
        assigned_drive=drive_name,
        assigned_tape_id=None if tape is None else tape["id"],
    )

    try:
        with _lock(config, "changer"):
            with closing(db.connect(config)) as connection:
                with connection:
                    db.transition_job(
                        connection,
                        job["id"],
                        "unloading",
                        event_type="before_mtx_unload",
                        message="About to unload tape from drive.",
                        data={
                            "command": [
                                "mtx",
                                "-f",
                                _changer(config),
                                "unload",
                                str(slot),
                                str(drive_index),
                            ]
                        },
                    )

            _run(["mtx", "-f", _changer(config), "unload", str(slot), str(drive_index)])

        database = _refresh_inventory(config)
        _complete_job(config, job["id"], "Tape unloaded.", database)
        return _job(config, job["id"])
    except ExecutionError as exc:
        _fail_job(config, job["id"], str(exc))
        raise


def mount_ltfs(
    config: dict[str, Any], drive_name: str, *, read_only: bool = True
) -> dict[str, Any]:
    drive_index, drive = _configured_drive(config, drive_name)
    mount_path = drive["mountPath"]
    sg_device = drive.get("sgDevice") or hardware.sg_device_for_st_device(
        drive["stDevice"]
    )
    if sg_device is None:
        raise ExecutionError(
            f"No SCSI generic device could be resolved for {drive_name}."
        )

    job = _create_job(
        config,
        "mount_ltfs",
        source={"drive": drive_name, "drive_index": drive_index, "sgDevice": sg_device},
        target={"mountPath": mount_path, "readOnly": read_only},
        assigned_drive=drive_name,
    )

    try:
        with _lock(config, f"drive-{drive_name}"):
            Path(mount_path).mkdir(parents=True, exist_ok=True)
            ltfs_options = f"devname={sg_device}"
            if read_only:
                ltfs_options = f"{ltfs_options},ro"
            command = ["ltfs", "-o", ltfs_options, mount_path]
            with closing(db.connect(config)) as connection:
                with connection:
                    db.transition_job(
                        connection,
                        job["id"],
                        "mounting_ltfs",
                        event_type="before_ltfs_mount",
                        message="About to mount LTFS.",
                        data={"command": command},
                    )
            _run(command)

        _complete_job(config, job["id"], "LTFS mounted.", {"mountPath": mount_path})
        return _job(config, job["id"])
    except ExecutionError as exc:
        _fail_job(config, job["id"], str(exc))
        raise


def unmount_ltfs(config: dict[str, Any], drive_name: str) -> dict[str, Any]:
    _drive_index, drive = _configured_drive(config, drive_name)
    mount_path = drive["mountPath"]
    job = _create_job(
        config,
        "unmount_ltfs",
        source={"mountPath": mount_path},
        target={"drive": drive_name},
        assigned_drive=drive_name,
    )

    try:
        with _lock(config, f"drive-{drive_name}"):
            command = ["fusermount", "-u", mount_path]
            with closing(db.connect(config)) as connection:
                with connection:
                    db.transition_job(
                        connection,
                        job["id"],
                        "unmounting",
                        event_type="before_ltfs_unmount",
                        message="About to unmount LTFS.",
                        data={"command": command},
                    )
            try:
                _run(command)
            except ExecutionError:
                _run(["umount", mount_path])

        _complete_job(config, job["id"], "LTFS unmounted.", {"mountPath": mount_path})
        return _job(config, job["id"])
    except ExecutionError as exc:
        _fail_job(config, job["id"], str(exc))
        raise


def reconcile_hardware_jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    db.initialize_database(config)
    inventory = _refresh_inventory(config)
    active_states = tuple(sorted(db.ACTIVE_JOB_STATES))
    placeholders = ", ".join("?" for _ in active_states)
    reconciled: list[dict[str, Any]] = []
    with closing(db.connect(config)) as connection:
        jobs = connection.execute(
            f"SELECT * FROM jobs WHERE state IN ({placeholders}) ORDER BY created_at",
            active_states,
        ).fetchall()
        with connection:
            for row in jobs:
                job = db.decode_job_row(row)
                outcome = _reconcile_job(connection, inventory, job)
                if outcome is not None:
                    reconciled.append(outcome)
    return reconciled


def _create_job(
    config: dict[str, Any],
    job_type: str,
    *,
    source: Any,
    target: Any,
    assigned_drive: str | None = None,
    assigned_tape_id: int | None = None,
) -> dict[str, Any]:
    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        with connection:
            return db.create_job_with_connection(
                connection,
                job_type,
                state="queued",
                source=source,
                target=target,
                assigned_drive=assigned_drive,
                assigned_tape_id=assigned_tape_id,
            )


def _complete_job(config: dict[str, Any], job_id: str, message: str, data: Any) -> None:
    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job_id,
                "complete",
                event_type="job_complete",
                message=message,
                data=data,
            )


def _fail_job(config: dict[str, Any], job_id: str, message: str) -> None:
    with closing(db.connect(config)) as connection:
        with connection:
            db.transition_job(
                connection,
                job_id,
                "failed",
                event_type="job_failed",
                message=message,
                data=None,
                last_error=message,
            )


def _job(config: dict[str, Any], job_id: str) -> dict[str, Any]:
    with closing(db.connect(config)) as connection:
        return db.get_job(connection, job_id)


def _refresh_inventory(config: dict[str, Any]) -> dict[str, Any]:
    inventory = hardware.read_changer_inventory(_changer(config)).as_dict()
    if inventory.get("error") is not None:
        raise ExecutionError(inventory["error"])
    db.apply_changer_inventory(config, inventory)
    return inventory


def _reconcile_job(connection, inventory: dict[str, Any], job: dict[str, Any]):
    job_type = job["type"]
    previous_state = job["state"]
    if job_type == "mount_ltfs" and _is_mounted(job["target"]["mountPath"]):
        db.transition_job(
            connection,
            job["id"],
            "complete",
            event_type="hardware_reconciled",
            message="LTFS mount was found active after an interrupted command.",
            data={
                "previous_state": previous_state,
                "mountPath": job["target"]["mountPath"],
            },
        )
        return {**job, "state": "complete", "previous_state": previous_state}

    if job_type == "unmount_ltfs" and not _is_mounted(job["source"]["mountPath"]):
        db.transition_job(
            connection,
            job["id"],
            "complete",
            event_type="hardware_reconciled",
            message="LTFS mount was already absent during reconciliation.",
            data={
                "previous_state": previous_state,
                "mountPath": job["source"]["mountPath"],
            },
        )
        return {**job, "state": "complete", "previous_state": previous_state}

    if job_type == "load_tape":
        drive_index = int(job["target"]["drive_index"])
        drive = _drive_status(inventory, drive_index)
        if drive is not None and drive.get("barcode") == job["source"]["barcode"]:
            db.transition_job(
                connection,
                job["id"],
                "complete",
                event_type="hardware_reconciled",
                message="Requested tape is present in the target drive.",
                data={"previous_state": previous_state, "drive": drive},
            )
            return {**job, "state": "complete", "previous_state": previous_state}

    if job_type == "unload_tape":
        drive_index = int(job["source"]["drive_index"])
        drive = _drive_status(inventory, drive_index)
        if drive is not None and drive.get("state") == "empty":
            db.transition_job(
                connection,
                job["id"],
                "complete",
                event_type="hardware_reconciled",
                message="Target drive is empty after unload reconciliation.",
                data={"previous_state": previous_state, "drive": drive},
            )
            return {**job, "state": "complete", "previous_state": previous_state}

    db.transition_job(
        connection,
        job["id"],
        "needs_operator",
        event_type="hardware_reconcile_needed",
        message="Could not prove the active hardware job completed.",
        data={"previous_state": previous_state},
        last_error="Hardware reconciliation could not prove completion.",
    )
    return {**job, "state": "needs_operator", "previous_state": previous_state}


def _is_mounted(path: str) -> bool:
    completed = subprocess.run(
        ["findmnt", "-n", "--target", path],
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def _changer(config: dict[str, Any]) -> str:
    changer = config.get("library", {}).get("changerDevice")
    if changer is None:
        raise ExecutionError("No changer device is configured.")
    return changer


def _configured_drive(
    config: dict[str, Any], drive_name: str
) -> tuple[int, dict[str, Any]]:
    drives = config.get("library", {}).get("drives", [])
    for index, drive in enumerate(drives):
        if drive["name"] == drive_name:
            return index, drive
    raise ExecutionError(f"Unknown drive {drive_name}.")


def _slot_for_barcode(inventory: dict[str, Any], barcode: str) -> dict[str, Any] | None:
    for slot in inventory.get("slots", []):
        if slot.get("barcode") == barcode and slot.get("state") == "full":
            return slot
    return None


def _drive_status(inventory: dict[str, Any], drive_index: int) -> dict[str, Any] | None:
    for drive in inventory.get("drives", []):
        if int(drive["index"]) == drive_index:
            return drive
    return None


def _require_drive_empty(inventory: dict[str, Any], drive_index: int) -> None:
    drive = _drive_status(inventory, drive_index)
    if drive is None:
        raise ExecutionError(
            f"Drive index {drive_index} was not reported by the changer."
        )
    if drive.get("state") != "empty":
        raise ExecutionError(f"Drive index {drive_index} is not empty.")


def _require_allowed_barcode(barcode: str, allowed_generations: list[str]) -> None:
    if not hardware.is_allowed_barcode(barcode, allowed_generations):
        raise ExecutionError(
            f"Tape {barcode} is not in allowed generations {allowed_generations}."
        )


@contextmanager
def _lock(config: dict[str, Any], name: str):
    lock_dir = Path(config.get("stateDir", "/var/lib/tapelib")) / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{name}.lock"
    with lock_path.open("w", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _run(command: list[str]) -> None:
    completed = subprocess.run(command, check=False, capture_output=True)
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        message = stderr.strip() or stdout.strip()
        raise ExecutionError(
            message
            or f"Command failed with exit code {completed.returncode}: {command}"
        )
