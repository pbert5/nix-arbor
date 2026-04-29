from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

ACTIVE_JOB_STATES = {
    "waiting_for_cache",
    "waiting_for_changer",
    "loading_tape",
    "mounting_ltfs",
    "running",
    "verifying",
    "updating_catalog",
    "unmounting",
    "unloading",
}


SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS tapes (
      id INTEGER PRIMARY KEY,
      barcode TEXT UNIQUE NOT NULL,
      ltfs_uuid TEXT,
      generation TEXT,
      slot INTEGER,
      current_location TEXT,
      state TEXT,
      capacity_bytes INTEGER,
      used_bytes INTEGER,
      free_bytes INTEGER,
      last_inventory_at TEXT,
      last_indexed_at TEXT,
      last_verified_at TEXT,
      dirty INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS files (
      id INTEGER PRIMARY KEY,
      tape_id INTEGER NOT NULL,
      path TEXT NOT NULL,
      logical_group TEXT,
      size_bytes INTEGER,
      mtime TEXT,
      checksum_sha256 TEXT,
      state TEXT,
      indexed_at TEXT,
      verified_at TEXT,
      UNIQUE(tape_id, path),
      FOREIGN KEY(tape_id) REFERENCES tapes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS jobs (
      id TEXT PRIMARY KEY,
      type TEXT NOT NULL,
      state TEXT NOT NULL,
      priority INTEGER NOT NULL DEFAULT 100,
      source_json TEXT,
      target_json TEXT,
      required_bytes INTEGER,
      assigned_drive TEXT,
      assigned_tape_id INTEGER,
      created_at TEXT NOT NULL,
      started_at TEXT,
      finished_at TEXT,
      last_error TEXT,
      retry_count INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY(assigned_tape_id) REFERENCES tapes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_events (
      id INTEGER PRIMARY KEY,
      job_id TEXT NOT NULL,
      event_type TEXT NOT NULL,
      message TEXT,
      data_json TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(job_id) REFERENCES jobs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS drives (
      id TEXT PRIMARY KEY,
      sg_device TEXT,
      st_device TEXT,
      mount_path TEXT,
      loaded_tape_id INTEGER,
      state TEXT,
      last_seen_at TEXT,
      FOREIGN KEY(loaded_tape_id) REFERENCES tapes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cache_entries (
      id INTEGER PRIMARY KEY,
      job_id TEXT,
      source_path TEXT,
      cache_path TEXT,
      size_bytes INTEGER,
      checksum_sha256 TEXT,
      state TEXT,
      created_at TEXT NOT NULL,
      FOREIGN KEY(job_id) REFERENCES jobs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inventory_snapshots (
      id INTEGER PRIMARY KEY,
      source_tape_id INTEGER,
      source_barcode TEXT,
      job_id TEXT,
      generated_at TEXT NOT NULL,
      imported_at TEXT NOT NULL,
      data_json TEXT NOT NULL,
      FOREIGN KEY(source_tape_id) REFERENCES tapes(id),
      FOREIGN KEY(job_id) REFERENCES jobs(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS inventory_observations (
      id INTEGER PRIMARY KEY,
      snapshot_id INTEGER NOT NULL,
      observed_barcode TEXT NOT NULL,
      observed_path TEXT,
      observed_state TEXT,
      observed_size_bytes INTEGER,
      observed_mtime TEXT,
      observed_checksum_sha256 TEXT,
      observed_at TEXT NOT NULL,
      FOREIGN KEY(snapshot_id) REFERENCES inventory_snapshots(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)",
    "CREATE INDEX IF NOT EXISTS idx_files_logical_group ON files(logical_group)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_state_priority ON jobs(state, priority, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_job_events_job_created ON job_events(job_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_cache_entries_job ON cache_entries(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_snapshots_barcode_generated ON inventory_snapshots(source_barcode, generated_at)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_observations_barcode_path ON inventory_observations(observed_barcode, observed_path)",
]


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def database_path(config: dict[str, Any]) -> Path:
    return Path(
        config.get("database", {}).get("path", "/var/lib/tapelib/catalog.sqlite")
    )


def connect(config: dict[str, Any]) -> sqlite3.Connection:
    path = database_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database(config: dict[str, Any]) -> dict[str, Any]:
    with closing(connect(config)) as connection:
        with connection:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            _upsert_configured_drives(connection, config)
        return database_summary(connection)


def _upsert_configured_drives(
    connection: sqlite3.Connection, config: dict[str, Any]
) -> None:
    for drive in config.get("library", {}).get("drives", []):
        connection.execute(
            """
            INSERT INTO drives (id, sg_device, st_device, mount_path, state, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              sg_device = excluded.sg_device,
              st_device = excluded.st_device,
              mount_path = excluded.mount_path,
              last_seen_at = excluded.last_seen_at
            """,
            (
                drive["name"],
                drive.get("sgDevice"),
                drive.get("stDevice"),
                drive.get("mountPath"),
                "configured",
                utc_now(),
            ),
        )


def database_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    counts = {}
    for table in [
        "tapes",
        "files",
        "jobs",
        "job_events",
        "drives",
        "cache_entries",
        "inventory_snapshots",
        "inventory_observations",
    ]:
        counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[
            0
        ]
    return {
        "path": connection.execute("PRAGMA database_list").fetchone()["file"],
        "schema_version": version,
        "counts": counts,
    }


def list_tapes(
    config: dict[str, Any], *, include_ignored: bool = False
) -> list[dict[str, Any]]:
    initialize_database(config)
    with closing(connect(config)) as connection:
        if include_ignored:
            rows = connection.execute("SELECT * FROM tapes ORDER BY barcode").fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM tapes WHERE state != 'ignored_generation' ORDER BY barcode"
            ).fetchall()
        return [dict(row) for row in rows]


def get_tape(config: dict[str, Any], barcode: str) -> dict[str, Any] | None:
    initialize_database(config)
    with closing(connect(config)) as connection:
        row = connection.execute(
            "SELECT * FROM tapes WHERE barcode = ?", (barcode,)
        ).fetchone()
        return None if row is None else dict(row)


def list_drives(config: dict[str, Any]) -> list[dict[str, Any]]:
    initialize_database(config)
    with closing(connect(config)) as connection:
        rows = connection.execute("SELECT * FROM drives ORDER BY id").fetchall()
        return [dict(row) for row in rows]


def get_drive(config: dict[str, Any], drive_id: str) -> dict[str, Any] | None:
    initialize_database(config)
    with closing(connect(config)) as connection:
        row = connection.execute(
            "SELECT * FROM drives WHERE id = ?", (drive_id,)
        ).fetchone()
        return None if row is None else dict(row)


def list_files(
    config: dict[str, Any], *, tape_barcode: str | None = None
) -> list[dict[str, Any]]:
    initialize_database(config)
    with closing(connect(config)) as connection:
        if tape_barcode is None:
            rows = connection.execute(
                """
                SELECT files.*, tapes.barcode AS tape_barcode
                FROM files
                JOIN tapes ON tapes.id = files.tape_id
                ORDER BY tapes.barcode, files.path
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT files.*, tapes.barcode AS tape_barcode
                FROM files
                JOIN tapes ON tapes.id = files.tape_id
                WHERE tapes.barcode = ?
                ORDER BY files.path
                """,
                (tape_barcode,),
            ).fetchall()
        return [dict(row) for row in rows]


def get_file(
    config: dict[str, Any], *, tape_barcode: str, path: str
) -> dict[str, Any] | None:
    initialize_database(config)
    clean_path = _clean_catalog_path(path)
    with closing(connect(config)) as connection:
        row = connection.execute(
            """
            SELECT files.*, tapes.barcode AS tape_barcode
            FROM files
            JOIN tapes ON tapes.id = files.tape_id
            WHERE tapes.barcode = ? AND files.path = ?
            """,
            (tape_barcode, clean_path),
        ).fetchone()
        return None if row is None else dict(row)


def apply_changer_inventory(
    config: dict[str, Any], inventory: dict[str, Any]
) -> dict[str, Any]:
    initialize_database(config)
    now = utc_now()
    with closing(connect(config)) as connection:
        with connection:
            for slot in inventory.get("slots", []):
                barcode = slot.get("barcode")
                if barcode is None:
                    continue
                generation = _barcode_generation(barcode)
                allowed_generations = config.get("library", {}).get(
                    "allowedGenerations", ["L5"]
                )
                if generation not in allowed_generations:
                    state = "ignored_generation"
                elif slot.get("import_export"):
                    state = "in_import_export"
                else:
                    state = "in_library"
                connection.execute(
                    """
                    INSERT INTO tapes (
                      barcode, slot, current_location, state, last_inventory_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(barcode) DO UPDATE SET
                      slot = excluded.slot,
                      current_location = excluded.current_location,
                      state = excluded.state,
                      last_inventory_at = excluded.last_inventory_at
                    """,
                    (barcode, slot.get("slot"), f"slot:{slot.get('slot')}", state, now),
                )

            configured_drives = config.get("library", {}).get("drives", [])
            for drive_status in inventory.get("drives", []):
                index = int(drive_status["index"])
                configured_drive = (
                    configured_drives[index] if index < len(configured_drives) else {}
                )
                drive_id = configured_drive.get("name", f"drive{index}")
                barcode = drive_status.get("barcode")
                tape_id = None
                if barcode is not None:
                    generation = _barcode_generation(barcode)
                    allowed_generations = config.get("library", {}).get(
                        "allowedGenerations", ["L5"]
                    )
                    tape_state = (
                        "loaded"
                        if generation in allowed_generations
                        else "ignored_generation"
                    )
                    connection.execute(
                        """
                        INSERT INTO tapes (
                          barcode, slot, current_location, state, last_inventory_at
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(barcode) DO UPDATE SET
                          slot = excluded.slot,
                          current_location = excluded.current_location,
                          state = excluded.state,
                          last_inventory_at = excluded.last_inventory_at
                        """,
                        (
                            barcode,
                            drive_status.get("source_slot"),
                            f"drive:{drive_id}",
                            tape_state,
                            now,
                        ),
                    )
                    tape_id = connection.execute(
                        "SELECT id FROM tapes WHERE barcode = ?", (barcode,)
                    ).fetchone()["id"]

                connection.execute(
                    """
                    INSERT INTO drives (
                      id, sg_device, st_device, mount_path, loaded_tape_id, state, last_seen_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      sg_device = excluded.sg_device,
                      st_device = excluded.st_device,
                      mount_path = excluded.mount_path,
                      loaded_tape_id = excluded.loaded_tape_id,
                      state = excluded.state,
                      last_seen_at = excluded.last_seen_at
                    """,
                    (
                        drive_id,
                        configured_drive.get("sgDevice"),
                        configured_drive.get("stDevice"),
                        configured_drive.get("mountPath"),
                        tape_id,
                        drive_status.get("state", "unknown"),
                        now,
                    ),
                )
        return database_summary(connection)


def create_job(
    config: dict[str, Any],
    job_type: str,
    *,
    priority: int = 100,
    source: Any = None,
    target: Any = None,
    required_bytes: int | None = None,
    assigned_drive: str | None = None,
    assigned_tape_id: int | None = None,
) -> dict[str, Any]:
    initialize_database(config)
    job_id = str(uuid.uuid4())
    created_at = utc_now()
    with closing(connect(config)) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO jobs (
                  id, type, state, priority, source_json, target_json,
                  required_bytes, assigned_drive, assigned_tape_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    job_type,
                    "created",
                    priority,
                    _json_or_none(source),
                    _json_or_none(target),
                    required_bytes,
                    assigned_drive,
                    assigned_tape_id,
                    created_at,
                ),
            )
            append_job_event(
                connection,
                job_id,
                "job_created",
                "Job created and persisted to the journal.",
                {"state": "created"},
            )
        return get_job(connection, job_id)


def create_job_with_connection(
    connection: sqlite3.Connection,
    job_type: str,
    *,
    state: str = "created",
    priority: int = 100,
    source: Any = None,
    target: Any = None,
    required_bytes: int | None = None,
    assigned_drive: str | None = None,
    assigned_tape_id: int | None = None,
) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    created_at = utc_now()
    connection.execute(
        """
        INSERT INTO jobs (
          id, type, state, priority, source_json, target_json,
          required_bytes, assigned_drive, assigned_tape_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            job_type,
            state,
            priority,
            _json_or_none(source),
            _json_or_none(target),
            required_bytes,
            assigned_drive,
            assigned_tape_id,
            created_at,
        ),
    )
    append_job_event(
        connection,
        job_id,
        "job_created",
        "Job created and persisted to the journal.",
        {"state": state},
    )
    return get_job(connection, job_id)


def find_matching_job(
    connection: sqlite3.Connection,
    job_type: str,
    *,
    states: list[str],
    source: Any = None,
    target: Any = None,
) -> dict[str, Any] | None:
    placeholders = ", ".join("?" for _ in states)
    row = connection.execute(
        f"""
        SELECT * FROM jobs
        WHERE type = ?
          AND state IN ({placeholders})
          AND source_json = ?
          AND target_json = ?
        ORDER BY priority, created_at
        LIMIT 1
        """,
        (
            job_type,
            *states,
            _json_or_none(source),
            _json_or_none(target),
        ),
    ).fetchone()
    return None if row is None else decode_job_row(row)


def append_job_event(
    connection: sqlite3.Connection,
    job_id: str,
    event_type: str,
    message: str | None = None,
    data: Any = None,
) -> None:
    connection.execute(
        """
        INSERT INTO job_events (job_id, event_type, message, data_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (job_id, event_type, message, _json_or_none(data), utc_now()),
    )


def transition_job(
    connection: sqlite3.Connection,
    job_id: str,
    state: str,
    *,
    event_type: str,
    message: str | None = None,
    data: Any = None,
    last_error: str | None = None,
) -> None:
    fields = ["state = ?"]
    values: list[Any] = [state]
    if state == "running":
        fields.append("started_at = COALESCE(started_at, ?)")
        values.append(utc_now())
    if state in {"cancelled", "complete", "failed"}:
        fields.append("finished_at = COALESCE(finished_at, ?)")
        values.append(utc_now())
    if last_error is not None:
        fields.append("last_error = ?")
        values.append(last_error)
    values.append(job_id)
    connection.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
    append_job_event(connection, job_id, event_type, message, data)


def reconcile_interrupted_jobs(config: dict[str, Any]) -> list[dict[str, Any]]:
    initialize_database(config)
    placeholders = ", ".join("?" for _ in ACTIVE_JOB_STATES)
    with closing(connect(config)) as connection:
        interrupted = connection.execute(
            f"SELECT * FROM jobs WHERE state IN ({placeholders}) ORDER BY priority, created_at",
            tuple(sorted(ACTIVE_JOB_STATES)),
        ).fetchall()
        with connection:
            for row in interrupted:
                transition_job(
                    connection,
                    row["id"],
                    "needs_operator",
                    event_type="daemon_startup_recovery",
                    message="Daemon restarted while this job was active; operator reconciliation is required.",
                    data={"previous_state": row["state"]},
                    last_error="Interrupted while active before daemon startup.",
                )
        return [decode_job_row(row) for row in interrupted]


def get_job(connection: sqlite3.Connection, job_id: str) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(job_id)
    return decode_job_row(row)


def list_jobs(
    config: dict[str, Any], *, state: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    initialize_database(config)
    with closing(connect(config)) as connection:
        if state is None:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY priority, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE state = ? ORDER BY priority, created_at DESC LIMIT ?",
                (state, limit),
            ).fetchall()
        return [decode_job_row(row) for row in rows]


def get_job_by_id(config: dict[str, Any], job_id: str) -> dict[str, Any]:
    initialize_database(config)
    with closing(connect(config)) as connection:
        return get_job(connection, job_id)


def list_job_events(
    config: dict[str, Any], *, job_id: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    initialize_database(config)
    with closing(connect(config)) as connection:
        if job_id is None:
            rows = connection.execute(
                "SELECT * FROM job_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        return [_decode_event(row) for row in rows]


def decode_job_row(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["source"] = _json_from_text(payload.pop("source_json"))
    payload["target"] = _json_from_text(payload.pop("target_json"))
    return payload


def _decode_event(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["data"] = _json_from_text(payload.pop("data_json"))
    return payload


def _json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True)


def _json_from_text(value: str | None) -> Any:
    if value is None:
        return None
    return json.loads(value)


def _clean_catalog_path(path: str) -> str:
    return str(Path("/") / path.lstrip("/")).lstrip("/")


def _barcode_generation(barcode: str) -> str | None:
    if len(barcode) < 2:
        return None
    return barcode[-2:]
