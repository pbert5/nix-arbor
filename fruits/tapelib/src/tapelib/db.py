from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 3

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
        """
        CREATE TABLE IF NOT EXISTS bundle_members (
            id INTEGER PRIMARY KEY,
            tape_id INTEGER NOT NULL,
            bundle_path TEXT NOT NULL,
            member_path TEXT NOT NULL,
            size_bytes INTEGER,
            checksum_sha256 TEXT,
            indexed_at TEXT NOT NULL,
            UNIQUE(tape_id, member_path),
            FOREIGN KEY(tape_id) REFERENCES tapes(id)
        )
        """,
    "CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)",
    "CREATE INDEX IF NOT EXISTS idx_files_logical_group ON files(logical_group)",
    "CREATE INDEX IF NOT EXISTS idx_jobs_state_priority ON jobs(state, priority, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_job_events_job_created ON job_events(job_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_cache_entries_job ON cache_entries(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_snapshots_barcode_generated ON inventory_snapshots(source_barcode, generated_at)",
    "CREATE INDEX IF NOT EXISTS idx_inventory_observations_barcode_path ON inventory_observations(observed_barcode, observed_path)",
        "CREATE INDEX IF NOT EXISTS idx_bundle_members_tape_member ON bundle_members(tape_id, member_path)",
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
        "bundle_members",
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


def list_bundle_members(
    config: dict[str, Any], *, tape_barcode: str | None = None
) -> list[dict[str, Any]]:
    initialize_database(config)
    with closing(connect(config)) as connection:
        if tape_barcode is None:
            rows = connection.execute(
                """
                SELECT bundle_members.*, tapes.barcode AS tape_barcode
                FROM bundle_members
                JOIN tapes ON tapes.id = bundle_members.tape_id
                ORDER BY tapes.barcode, bundle_members.member_path
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT bundle_members.*, tapes.barcode AS tape_barcode
                FROM bundle_members
                JOIN tapes ON tapes.id = bundle_members.tape_id
                WHERE tapes.barcode = ?
                ORDER BY bundle_members.member_path
                """,
                (tape_barcode,),
            ).fetchall()
        return [dict(row) for row in rows]


def upsert_bundle_members_with_connection(
    connection: sqlite3.Connection,
    tape_id: int,
    bundle_path: str,
    members: list[dict[str, Any]],
    *,
    indexed_at: str,
) -> None:
    for member in members:
        connection.execute(
            """
            INSERT INTO bundle_members (
              tape_id, bundle_path, member_path, size_bytes,
              checksum_sha256, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(tape_id, member_path) DO UPDATE SET
              bundle_path = excluded.bundle_path,
              size_bytes = excluded.size_bytes,
              checksum_sha256 = excluded.checksum_sha256,
              indexed_at = excluded.indexed_at
            """,
            (
                tape_id,
                _clean_catalog_path(bundle_path),
                _clean_catalog_path(member["member_path"]),
                member.get("size_bytes"),
                member.get("checksum_sha256"),
                indexed_at,
            ),
        )


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


def index_tape(
    config: dict[str, Any],
    barcode: str,
    mount_path: str,
) -> dict[str, Any]:
    """Walk a mounted LTFS tape and upsert file records into the catalog.

    Files that were previously indexed but are no longer present on the tape
    are marked ``missing_after_reindex`` rather than deleted, so history is
    preserved and anomalies are surfaced explicitly.
    """
    initialize_database(config)
    now = utc_now()
    mount_root = Path(mount_path)

    # File/directory names at the tape root that belong to tapelib housekeeping
    # and should not be indexed as content.
    skip_names = {
        "TAPELIB-INVENTORY.json",
        "TAPE-MANIFEST.json",
        "TAPE-MANIFEST.csv",
        "TAPE-CHECKSUMS.sha256",
        "README-THIS-TAPE.txt",
    }
    # Path prefixes (first component) that are always internal
    skip_prefixes = {".tapelib-writing"}

    if not mount_root.is_dir():
        raise ValueError(f"Mount path not found or not a directory: {mount_path}")

    with closing(connect(config)) as connection:
        with connection:
            # Ensure tape record exists; update last_indexed_at.
            connection.execute(
                """
                INSERT INTO tapes (barcode, current_location, state, last_indexed_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(barcode) DO UPDATE SET
                  last_indexed_at = excluded.last_indexed_at
                """,
                (barcode, f"indexed_at:{mount_path}", "indexed", now),
            )
            tape_id = connection.execute(
                "SELECT id FROM tapes WHERE barcode = ?", (barcode,)
            ).fetchone()["id"]

            # Paths already in the catalog for this tape.
            existing_paths: set[str] = {
                row[0]
                for row in connection.execute(
                    "SELECT path FROM files WHERE tape_id = ?", (tape_id,)
                ).fetchall()
            }
            discovered_bundle_members: list[dict[str, Any]] = []

            seen_paths: set[str] = set()
            indexed_count = 0

            for file_path in sorted(mount_root.rglob("*")):
                if not file_path.is_file():
                    continue
                relative = str(file_path.relative_to(mount_root))
                first_component = relative.split("/")[0]
                if first_component in skip_names or first_component in skip_prefixes:
                    continue
                if first_component.startswith("."):
                    continue

                seen_paths.add(relative)
                st = file_path.stat()
                mtime = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)
                )

                connection.execute(
                    """
                    INSERT INTO files (tape_id, path, size_bytes, mtime, state, indexed_at)
                    VALUES (?, ?, ?, ?, 'indexed', ?)
                    ON CONFLICT(tape_id, path) DO UPDATE SET
                      size_bytes = excluded.size_bytes,
                      mtime     = excluded.mtime,
                      state     = 'indexed',
                      indexed_at = excluded.indexed_at
                    """,
                    (tape_id, relative, st.st_size, mtime, now),
                )
                indexed_count += 1

                discovered_bundle_members.extend(
                    _bundle_members_from_manifest(file_path, relative, now)
                )

            # Mark files that vanished since the last index.
            missing_count = 0
            for path in existing_paths:
                if path not in seen_paths:
                    connection.execute(
                        """
                        UPDATE files SET state = 'missing_after_reindex'
                        WHERE tape_id = ? AND path = ?
                        """,
                        (tape_id, path),
                    )
                    missing_count += 1

            connection.execute(
                "DELETE FROM bundle_members WHERE tape_id = ?",
                (tape_id,),
            )
            bundle_members_by_bundle: dict[str, list[dict[str, Any]]] = {}
            for member in discovered_bundle_members:
                bundle_members_by_bundle.setdefault(member["bundle_path"], []).append(member)
            for bundle_path, members in bundle_members_by_bundle.items():
                upsert_bundle_members_with_connection(
                    connection,
                    tape_id,
                    bundle_path,
                    members,
                    indexed_at=now,
                )

            connection.execute(
                "UPDATE tapes SET last_indexed_at = ? WHERE id = ?",
                (now, tape_id),
            )

    return {
        "tape_barcode": barcode,
        "mount_path": mount_path,
        "indexed_at": now,
        "indexed_count": indexed_count,
        "missing_count": missing_count,
    }


def get_or_create_tape(
    connection: sqlite3.Connection,
    barcode: str,
    *,
    state: str = "in_library",
) -> int:
    """Return the ``id`` for a tape row, inserting a minimal record if absent."""
    connection.execute(
        """
        INSERT INTO tapes (barcode, current_location, state, last_inventory_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(barcode) DO NOTHING
        """,
        (barcode, "unknown", state, utc_now()),
    )
    return connection.execute(
        "SELECT id FROM tapes WHERE barcode = ?", (barcode,)
    ).fetchone()["id"]


def import_inventory_manifest(
        config: dict[str, Any],
        manifest: dict[str, Any],
        *,
        source_barcode: str | None = None,
        source_path: str | None = None,
        job_id: str | None = None,
) -> dict[str, Any]:
        """Import a tape-carried inventory manifest additively.

        The import is intentionally conservative:
        - direct indexed / verified catalog rows are never downgraded
        - advisory imported rows are inserted when absent
        - advisory imported rows are refreshed when the imported snapshot is newer
        """
        initialize_database(config)
        imported_at = utc_now()
        generated_at = manifest.get("generated_at") or imported_at
        tapes = manifest.get("tapes", [])
        files = manifest.get("files", [])

        with closing(connect(config)) as connection:
                with connection:
                        source_tape_id = (
                                get_or_create_tape(connection, source_barcode)
                                if isinstance(source_barcode, str) and source_barcode
                                else None
                        )
                        cursor = connection.execute(
                                """
                                INSERT INTO inventory_snapshots (
                                    source_tape_id, source_barcode, job_id, generated_at, imported_at, data_json
                                ) VALUES (?, ?, ?, ?, ?, ?)
                                """,
                                (
                                        source_tape_id,
                                        source_barcode,
                                        job_id,
                                        generated_at,
                                        imported_at,
                                        json.dumps(manifest, sort_keys=True),
                                ),
                        )
                        snapshot_id = cursor.lastrowid

                        imported_tapes = 0
                        imported_files = 0

                        for tape in tapes:
                                barcode = tape.get("barcode")
                                if not isinstance(barcode, str) or not barcode:
                                        continue
                                connection.execute(
                                        """
                                        INSERT INTO inventory_observations (
                                            snapshot_id, observed_barcode, observed_path, observed_state,
                                            observed_size_bytes, observed_mtime, observed_checksum_sha256, observed_at
                                        ) VALUES (?, ?, NULL, ?, NULL, NULL, NULL, ?)
                                        """,
                                        (
                                                snapshot_id,
                                                barcode,
                                                tape.get("state"),
                                                generated_at,
                                        ),
                                )
                                connection.execute(
                                        """
                                        INSERT INTO tapes (
                                            barcode, generation, slot, current_location, state,
                                            capacity_bytes, used_bytes, free_bytes, last_inventory_at
                                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                        ON CONFLICT(barcode) DO UPDATE SET
                                            generation = COALESCE(tapes.generation, excluded.generation),
                                            capacity_bytes = COALESCE(tapes.capacity_bytes, excluded.capacity_bytes),
                                            used_bytes = COALESCE(tapes.used_bytes, excluded.used_bytes),
                                            free_bytes = COALESCE(tapes.free_bytes, excluded.free_bytes),
                                            last_inventory_at = CASE
                                                WHEN tapes.last_inventory_at IS NULL OR tapes.last_inventory_at <= excluded.last_inventory_at
                                                    THEN excluded.last_inventory_at
                                                ELSE tapes.last_inventory_at
                                            END,
                                            slot = COALESCE(tapes.slot, excluded.slot),
                                            current_location = COALESCE(tapes.current_location, excluded.current_location),
                                            state = CASE
                                                WHEN tapes.state IN ('indexed', 'verified', 'loaded') THEN tapes.state
                                                WHEN tapes.last_inventory_at IS NULL OR tapes.last_inventory_at <= excluded.last_inventory_at
                                                    THEN COALESCE(excluded.state, tapes.state)
                                                ELSE tapes.state
                                            END
                                        """,
                                        (
                                                barcode,
                                                tape.get("generation"),
                                                tape.get("slot"),
                                                tape.get("current_location"),
                                                tape.get("state") or "inventory_imported",
                                                tape.get("capacity_bytes"),
                                                tape.get("used_bytes"),
                                                tape.get("free_bytes"),
                                                generated_at,
                                        ),
                                )
                                imported_tapes += 1

                        for file_row in files:
                                barcode = file_row.get("tape_barcode") or file_row.get("barcode")
                                path = file_row.get("path")
                                if not isinstance(barcode, str) or not barcode or not isinstance(path, str) or not path:
                                        continue
                                tape_id = get_or_create_tape(connection, barcode)
                                connection.execute(
                                        """
                                        INSERT INTO inventory_observations (
                                            snapshot_id, observed_barcode, observed_path, observed_state,
                                            observed_size_bytes, observed_mtime, observed_checksum_sha256, observed_at
                                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                        """,
                                        (
                                                snapshot_id,
                                                barcode,
                                                path,
                                                file_row.get("state") or "inventory_imported",
                                                file_row.get("size_bytes"),
                                                file_row.get("mtime"),
                                                file_row.get("checksum_sha256"),
                                                generated_at,
                                        ),
                                )
                                connection.execute(
                                        """
                                        INSERT INTO files (
                                            tape_id, path, logical_group, size_bytes, mtime,
                                            checksum_sha256, state, indexed_at
                                        ) VALUES (?, ?, ?, ?, ?, ?, 'inventory_imported', ?)
                                        ON CONFLICT(tape_id, path) DO UPDATE SET
                                            size_bytes = CASE
                                                WHEN files.state = 'inventory_imported' AND (files.indexed_at IS NULL OR files.indexed_at <= excluded.indexed_at)
                                                    THEN excluded.size_bytes
                                                ELSE files.size_bytes
                                            END,
                                            mtime = CASE
                                                WHEN files.state = 'inventory_imported' AND (files.indexed_at IS NULL OR files.indexed_at <= excluded.indexed_at)
                                                    THEN excluded.mtime
                                                ELSE files.mtime
                                            END,
                                            checksum_sha256 = CASE
                                                WHEN files.state = 'inventory_imported' AND (files.indexed_at IS NULL OR files.indexed_at <= excluded.indexed_at)
                                                    THEN excluded.checksum_sha256
                                                ELSE files.checksum_sha256
                                            END,
                                            indexed_at = CASE
                                                WHEN files.state = 'inventory_imported' AND (files.indexed_at IS NULL OR files.indexed_at <= excluded.indexed_at)
                                                    THEN excluded.indexed_at
                                                ELSE files.indexed_at
                                            END,
                                            state = CASE
                                                WHEN files.state IN ('indexed', 'verified') THEN files.state
                                                WHEN files.state = 'inventory_imported' AND (files.indexed_at IS NULL OR files.indexed_at <= excluded.indexed_at)
                                                    THEN 'inventory_imported'
                                                ELSE files.state
                                            END
                                        """,
                                        (
                                                tape_id,
                                                _clean_catalog_path(path),
                                                file_row.get("logical_group"),
                                                file_row.get("size_bytes"),
                                                file_row.get("mtime"),
                                                file_row.get("checksum_sha256"),
                                                generated_at,
                                        ),
                                )
                                imported_files += 1

        return {
                "imported_at": imported_at,
                "generated_at": generated_at,
                "source_barcode": source_barcode,
                "source_path": source_path,
                "snapshot_id": snapshot_id,
                "tape_count": imported_tapes,
                "file_count": imported_files,
        }


def _clean_catalog_path(path: str) -> str:
    return str(Path("/") / path.lstrip("/")).lstrip("/")


def _bundle_members_from_manifest(
    manifest_path: Path,
    relative_path: str,
    indexed_at: str,
) -> list[dict[str, Any]]:
    if not relative_path.endswith(".members.json"):
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if manifest.get("format") != "tapelib-tar-bundle-v1":
        return []

    bundle_path = manifest.get("bundle_path")
    if not isinstance(bundle_path, str) or bundle_path == "":
        bundle_path = relative_path.removesuffix(".members.json") + ".tar"

    members = []
    for member in manifest.get("members", []):
        member_path = member.get("member_path") or member.get("path")
        if not isinstance(member_path, str) or member_path == "":
            continue
        members.append(
            {
                "bundle_path": _clean_catalog_path(bundle_path),
                "member_path": _clean_catalog_path(member_path),
                "size_bytes": member.get("size_bytes"),
                "checksum_sha256": member.get("checksum_sha256"),
                "indexed_at": indexed_at,
            }
        )
    return members


def _barcode_generation(barcode: str) -> str | None:
    if len(barcode) < 2:
        return None
    return barcode[-2:]
