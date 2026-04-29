"""Tests for database initialization, job lifecycle, and index_tape."""
from __future__ import annotations

from contextlib import closing

import pytest

from tapelib import db


def _config(tmp_path):
    return {
        "stateDir": str(tmp_path / "state"),
        "database": {"path": str(tmp_path / "catalog.sqlite")},
        "library": {"drives": [], "allowedGenerations": ["L5"]},
    }


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------


def test_initialize_is_idempotent(tmp_path):
    config = _config(tmp_path)
    s1 = db.initialize_database(config)
    s2 = db.initialize_database(config)
    assert s1["schema_version"] == s2["schema_version"] == db.SCHEMA_VERSION


def test_schema_tables_created(tmp_path):
    config = _config(tmp_path)
    db.initialize_database(config)
    with closing(db.connect(config)) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    for expected in ("tapes", "files", "jobs", "job_events", "drives", "cache_entries"):
        assert expected in tables


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


def test_create_and_retrieve_job(tmp_path):
    config = _config(tmp_path)
    job = db.create_job(
        config, "test_job", source={"foo": "bar"}, target={"baz": 1}
    )
    assert job["type"] == "test_job"
    assert job["state"] == "created"
    assert job["source"] == {"foo": "bar"}
    assert job["target"] == {"baz": 1}
    retrieved = db.get_job_by_id(config, job["id"])
    assert retrieved["id"] == job["id"]


def test_transition_job_state(tmp_path):
    config = _config(tmp_path)
    job = db.create_job(config, "test_job")
    with closing(db.connect(config)) as conn:
        with conn:
            db.transition_job(
                conn, job["id"], "running",
                event_type="started", message="test"
            )
    updated = db.get_job_by_id(config, job["id"])
    assert updated["state"] == "running"
    assert updated["started_at"] is not None


def test_complete_job_sets_finished_at(tmp_path):
    config = _config(tmp_path)
    job = db.create_job(config, "test_job")
    with closing(db.connect(config)) as conn:
        with conn:
            db.transition_job(conn, job["id"], "complete",
                              event_type="done", message="ok")
    updated = db.get_job_by_id(config, job["id"])
    assert updated["state"] == "complete"
    assert updated["finished_at"] is not None


def test_list_jobs_by_state(tmp_path):
    config = _config(tmp_path)
    j1 = db.create_job(config, "type_a")
    j2 = db.create_job(config, "type_b")
    with closing(db.connect(config)) as conn:
        with conn:
            db.transition_job(conn, j1["id"], "complete",
                              event_type="done", message="")
    queued = db.list_jobs(config, state="created")
    assert any(j["id"] == j2["id"] for j in queued)
    assert not any(j["id"] == j1["id"] for j in queued)


def test_reconcile_interrupted_jobs(tmp_path):
    config = _config(tmp_path)
    job = db.create_job(config, "hardware_op")
    with closing(db.connect(config)) as conn:
        with conn:
            db.transition_job(conn, job["id"], "running",
                              event_type="start", message="")
    reconciled = db.reconcile_interrupted_jobs(config)
    assert any(r["id"] == job["id"] for r in reconciled)
    updated = db.get_job_by_id(config, job["id"])
    assert updated["state"] == "needs_operator"


# ---------------------------------------------------------------------------
# index_tape
# ---------------------------------------------------------------------------


def _seed_tape(config, barcode):
    db.initialize_database(config)
    with closing(db.connect(config)) as conn:
        with conn:
            conn.execute(
                "INSERT INTO tapes (barcode, current_location, state) VALUES (?, ?, ?)",
                (barcode, "slot:1", "in_library"),
            )


def test_index_tape_discovers_files(tmp_path):
    config = _config(tmp_path)
    _seed_tape(config, "TAPE001L5")

    mount = tmp_path / "mount"
    (mount / "games" / "Nintendo").mkdir(parents=True)
    (mount / "games" / "Nintendo" / "mario.zip").write_bytes(b"fake content")
    (mount / "games" / "PC" / "quake.zip").parent.mkdir(parents=True)
    (mount / "games" / "PC" / "quake.zip").write_bytes(b"more fake content")

    result = db.index_tape(config, "TAPE001L5", str(mount))

    assert result["tape_barcode"] == "TAPE001L5"
    assert result["indexed_count"] == 2
    assert result["missing_count"] == 0

    files = db.list_files(config, tape_barcode="TAPE001L5")
    paths = {f["path"] for f in files}
    assert "games/Nintendo/mario.zip" in paths
    assert "games/PC/quake.zip" in paths


def test_index_tape_skips_internal_files(tmp_path):
    config = _config(tmp_path)
    _seed_tape(config, "TAPE001L5")

    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "TAPE-MANIFEST.json").write_text("{}", encoding="utf-8")
    (mount / "README-THIS-TAPE.txt").write_text("hi", encoding="utf-8")
    (mount / "TAPE-CHECKSUMS.sha256").write_text("", encoding="utf-8")
    (mount / "TAPELIB-INVENTORY.json").write_text("{}", encoding="utf-8")
    (mount / ".tapelib-writing").mkdir()
    (mount / ".tapelib-writing" / "partial.bin").write_bytes(b"\x00")
    (mount / "real-data.bin").write_bytes(b"real")

    result = db.index_tape(config, "TAPE001L5", str(mount))
    assert result["indexed_count"] == 1
    files = db.list_files(config, tape_barcode="TAPE001L5")
    assert files[0]["path"] == "real-data.bin"


def test_index_tape_marks_missing_files(tmp_path):
    config = _config(tmp_path)
    _seed_tape(config, "TAPE001L5")

    mount = tmp_path / "mount"
    mount.mkdir()

    # First index with two files.
    (mount / "a.bin").write_bytes(b"a")
    (mount / "b.bin").write_bytes(b"b")
    db.index_tape(config, "TAPE001L5", str(mount))

    # Remove b.bin and re-index.
    (mount / "b.bin").unlink()
    result = db.index_tape(config, "TAPE001L5", str(mount))

    assert result["indexed_count"] == 1
    assert result["missing_count"] == 1

    files = {f["path"]: f["state"] for f in db.list_files(config, tape_barcode="TAPE001L5")}
    assert files["a.bin"] == "indexed"
    assert files["b.bin"] == "missing_after_reindex"


def test_index_tape_upserts_size(tmp_path):
    config = _config(tmp_path)
    _seed_tape(config, "TAPE001L5")

    mount = tmp_path / "mount"
    mount.mkdir()
    (mount / "file.bin").write_bytes(b"x" * 100)
    db.index_tape(config, "TAPE001L5", str(mount))

    (mount / "file.bin").write_bytes(b"x" * 200)
    db.index_tape(config, "TAPE001L5", str(mount))

    files = db.list_files(config, tape_barcode="TAPE001L5")
    assert files[0]["size_bytes"] == 200


def test_index_tape_imports_bundle_member_manifests(tmp_path):
    config = _config(tmp_path)
    _seed_tape(config, "TAPE001L5")

    mount = tmp_path / "mount"
    bundle_dir = mount / "games" / "_tapelib-bundles"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "bundle-0001.tar").write_bytes(b"fake-tar")
    (bundle_dir / "bundle-0001.members.json").write_text(
        '{\n'
        '  "format": "tapelib-tar-bundle-v1",\n'
        '  "bundle_path": "games/_tapelib-bundles/bundle-0001.tar",\n'
        '  "members": [\n'
        '    {"member_path": "games/foo/a.txt", "size_bytes": 11, "checksum_sha256": "aaa"},\n'
        '    {"member_path": "games/foo/b.txt", "size_bytes": 22, "checksum_sha256": "bbb"}\n'
        '  ]\n'
        '}\n',
        encoding="utf-8",
    )

    db.index_tape(config, "TAPE001L5", str(mount))

    members = db.list_bundle_members(config, tape_barcode="TAPE001L5")
    assert {member["member_path"] for member in members} == {
        "games/foo/a.txt",
        "games/foo/b.txt",
    }


# ---------------------------------------------------------------------------
# get_or_create_tape
# ---------------------------------------------------------------------------


def test_get_or_create_tape_new(tmp_path):
    config = _config(tmp_path)
    db.initialize_database(config)
    with closing(db.connect(config)) as conn:
        with conn:
            tape_id = db.get_or_create_tape(conn, "NEW001L5")
    assert isinstance(tape_id, int)


def test_get_or_create_tape_existing(tmp_path):
    config = _config(tmp_path)
    db.initialize_database(config)
    with closing(db.connect(config)) as conn:
        with conn:
            id1 = db.get_or_create_tape(conn, "EXIST001L5")
            id2 = db.get_or_create_tape(conn, "EXIST001L5")
    assert id1 == id2


# ---------------------------------------------------------------------------
# import_inventory_manifest
# ---------------------------------------------------------------------------


def test_import_inventory_manifest_adds_advisory_rows(tmp_path):
    config = _config(tmp_path)
    manifest = {
        "generated_at": "2026-04-29T00:00:00Z",
        "tapes": [
            {
                "barcode": "TAPE999L5",
                "generation": "L5",
                "state": "inventory_imported",
            }
        ],
        "files": [
            {
                "tape_barcode": "TAPE999L5",
                "path": "games/example.bin",
                "size_bytes": 123,
                "checksum_sha256": "abc123",
            }
        ],
    }

    result = db.import_inventory_manifest(
        config,
        manifest,
        source_barcode="SRC001L5",
        source_path="/mnt/tape/TAPELIB-INVENTORY.json",
    )

    assert result["tape_count"] == 1
    assert result["file_count"] == 1

    tape = db.get_tape(config, "TAPE999L5")
    assert tape is not None
    files = db.list_files(config, tape_barcode="TAPE999L5")
    assert len(files) == 1
    assert files[0]["path"] == "games/example.bin"
    assert files[0]["state"] == "inventory_imported"


def test_import_inventory_manifest_does_not_downgrade_verified_rows(tmp_path):
    config = _config(tmp_path)
    db.initialize_database(config)
    with closing(db.connect(config)) as conn:
        with conn:
            tape_id = db.get_or_create_tape(conn, "TAPE777L5")
            conn.execute(
                """
                INSERT INTO files (
                  tape_id, path, size_bytes, checksum_sha256, state, indexed_at, verified_at
                ) VALUES (?, ?, ?, ?, 'verified', ?, ?)
                """,
                (
                    tape_id,
                    "games/example.bin",
                    999,
                    "real-checksum",
                    "2026-04-29T01:00:00Z",
                    "2026-04-29T01:00:00Z",
                ),
            )

    manifest = {
        "generated_at": "2026-04-28T00:00:00Z",
        "tapes": [{"barcode": "TAPE777L5", "generation": "L5"}],
        "files": [
            {
                "tape_barcode": "TAPE777L5",
                "path": "games/example.bin",
                "size_bytes": 123,
                "checksum_sha256": "imported-checksum",
            }
        ],
    }

    db.import_inventory_manifest(config, manifest)

    files = db.list_files(config, tape_barcode="TAPE777L5")
    assert len(files) == 1
    assert files[0]["state"] == "verified"
    assert files[0]["size_bytes"] == 999
    assert files[0]["checksum_sha256"] == "real-checksum"
