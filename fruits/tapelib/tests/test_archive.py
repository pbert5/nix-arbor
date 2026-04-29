"""Tests for archive.py — staging and write-to-tape logic."""
from __future__ import annotations

import json
import os
import subprocess
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

from tapelib import archive, db
from tapelib.archive import ArchiveError


def _config(tmp_path, cache_path=None):
    return {
        "stateDir": str(tmp_path / "state"),
        "database": {"path": str(tmp_path / "catalog.sqlite")},
        "cache": {"path": str(cache_path or (tmp_path / "cache"))},
        "archive": {
            "smallFileBundleMaxBytes": "0",
            "smallFileBundleTargetBytes": "256M",
        },
        "library": {
            "changerDevice": "/dev/test-changer",
            "drives": [
                {
                    "name": "drive0",
                    "stDevice": "/dev/nst0",
                    "mountPath": str(tmp_path / "drive0"),
                }
            ],
            "allowedGenerations": ["L5"],
        },
    }


def _make_plan(source_root: Path, tape: str, files: list[tuple[str, bytes]]) -> dict:
    """Build a minimal archive plan dict for testing."""
    assignments = []
    for logical_path, content in files:
        src = source_root / logical_path
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_bytes(content)
        assignments.append(
            {
                "tape": tape,
                "unit_path": str(Path(logical_path).parent),
                "size_bytes": len(content),
                "split": {"enabled": False, "part": 1},
                "files": [
                    {
                        "source_path": str(src),
                        "logical_path": logical_path,
                        "size_bytes": len(content),
                    }
                ],
            }
        )
    return {
        "generated_at": "2026-04-28T00:00:00Z",
        "namespace_prefix": "/games",
        "selected_tapes": [tape],
        "assignments": assignments,
    }


# ---------------------------------------------------------------------------
# stage_games_archive
# ---------------------------------------------------------------------------


def test_stage_copies_files_to_cache(tmp_path):
    config = _config(tmp_path)
    src = tmp_path / "source"
    plan = _make_plan(
        src,
        "385182L5",
        [
            ("Nintendo/mario.zip", b"mario"),
            ("PC/quake.zip", b"quake"),
        ],
    )
    db.initialize_database(config)

    jobs = archive.stage_games_archive(config, plan)

    assert len(jobs) == 1
    job = jobs[0]
    assert job["type"] == "write_archive"
    assert job["state"] == "queued"
    assert job["target"]["tape_barcode"] == "385182L5"

    staged_files = job["source"]["files"]
    assert len(staged_files) == 2
    for sf in staged_files:
        assert Path(sf["staging_path"]).is_file()
        assert sf["checksum_sha256"]


def test_stage_missing_source_raises(tmp_path):
    config = _config(tmp_path)
    db.initialize_database(config)
    plan = {
        "generated_at": "2026-01-01T00:00:00Z",
        "namespace_prefix": "/games",
        "selected_tapes": ["385182L5"],
        "assignments": [
            {
                "tape": "385182L5",
                "unit_path": "games",
                "size_bytes": 10,
                "split": {"enabled": False, "part": 1},
                "files": [
                    {
                        "source_path": str(tmp_path / "nonexistent.zip"),
                        "logical_path": "games/nonexistent.zip",
                        "size_bytes": 10,
                    }
                ],
            }
        ],
    }
    with pytest.raises(ArchiveError, match="Source file not found"):
        archive.stage_games_archive(config, plan)


def test_stage_creates_cache_entries(tmp_path):
    config = _config(tmp_path)
    src = tmp_path / "source"
    plan = _make_plan(src, "385182L5", [("games/test.zip", b"data")])
    db.initialize_database(config)
    jobs = archive.stage_games_archive(config, plan)
    job_id = jobs[0]["id"]

    with closing(db.connect(config)) as conn:
        rows = conn.execute(
            "SELECT * FROM cache_entries WHERE job_id = ?", (job_id,)
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["state"] == "staged"


def test_stage_empty_plan_raises(tmp_path):
    config = _config(tmp_path)
    db.initialize_database(config)
    empty_plan = {
        "generated_at": "2026-01-01T00:00:00Z",
        "namespace_prefix": "/games",
        "selected_tapes": [],
        "assignments": [],
    }
    with pytest.raises(ArchiveError, match="no tape assignments"):
        archive.stage_games_archive(config, empty_plan)


def test_stage_respects_budget_and_resumes_after_complete_write(tmp_path):
    config = _config(tmp_path)
    src = tmp_path / "source"
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)
    plan = _make_plan(
        src,
        "385182L5",
        [
            ("games/a.bin", b"a" * 5),
            ("games/b.bin", b"b" * 5),
        ],
    )

    first_jobs = archive.stage_games_archive(config, plan, max_staged_bytes=5)
    assert len(first_jobs) == 1
    assert [f["logical_path"] for f in first_jobs[0]["source"]["files"]] == [
        "games/a.bin"
    ]

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        archive.write_staged_archive(config, first_jobs[0])

    second_jobs = archive.stage_games_archive(config, plan, max_staged_bytes=5)
    assert len(second_jobs) == 1
    assert [f["logical_path"] for f in second_jobs[0]["source"]["files"]] == [
        "games/b.bin"
    ]


def test_write_archive_aggregates_manifests_and_cleans_cache(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)
    src = tmp_path / "source"
    plan = _make_plan(
        src,
        "385182L5",
        [
            ("games/a.bin", b"alpha"),
            ("games/b.bin", b"bravo"),
        ],
    )

    first_jobs = archive.stage_games_archive(config, plan, max_staged_bytes=5)
    second_jobs = archive.stage_games_archive(config, plan, max_staged_bytes=5)

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        archive.write_staged_archive(config, first_jobs[0])
        archive.write_staged_archive(config, second_jobs[0])

    manifest = json.loads((mount / "TAPE-MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["file_count"] == 2
    assert {entry["tape_path"] for entry in manifest["files"]} == {
        "games/games/a.bin",
        "games/games/b.bin",
    }

    first_staging_dir = Path(first_jobs[0]["source"]["staging_dir"])
    assert not first_staging_dir.exists()
    with closing(db.connect(config)) as conn:
        states = {
            row["state"]
            for row in conn.execute(
                "SELECT state FROM cache_entries WHERE job_id = ?",
                (first_jobs[0]["id"],),
            ).fetchall()
        }
    assert states == {"consumed"}


def test_cleanup_cache_keeps_unknown_staging_dirs(tmp_path):
    config = _config(tmp_path)
    db.initialize_database(config)
    active_dir = (
        Path(config["cache"]["path"])
        / "staging"
        / "archive-jobs"
        / "unknown-active-job"
        / "385182L5"
    )
    active_dir.mkdir(parents=True, exist_ok=True)
    marker = active_dir / "still-copying.bin"
    marker.write_bytes(b"in-progress")

    summary = archive.cleanup_cache(config)

    assert marker.exists()
    assert str(active_dir.parent) not in summary["removed_dirs"]


def test_stage_bundles_small_files_when_enabled(tmp_path):
    config = _config(tmp_path)
    config["archive"] = {
        "smallFileBundleMaxBytes": "10",
        "smallFileBundleTargetBytes": "32",
    }
    src = tmp_path / "source"
    plan = _make_plan(
        src,
        "385182L5",
        [
            ("games/a.bin", b"a" * 8),
            ("games/b.bin", b"b" * 8),
            ("games/c.bin", b"c" * 8),
        ],
    )

    jobs = archive.stage_games_archive(config, plan)

    write_units = jobs[0]["source"]["write_units"]
    bundle_units = [unit for unit in write_units if unit["kind"] == "bundle"]
    manifest_units = [unit for unit in write_units if unit["kind"] == "bundle_manifest"]

    assert len(bundle_units) == 1
    assert len(manifest_units) == 1
    assert Path(bundle_units[0]["staging_path"]).is_file()
    assert Path(manifest_units[0]["staging_path"]).is_file()
    assert len(bundle_units[0]["members"]) == 3
    assert all(file_row.get("bundled_in") for file_row in jobs[0]["source"]["files"])


# ---------------------------------------------------------------------------
# write_staged_archive
# ---------------------------------------------------------------------------


def _seed_tape_and_drive(config, tmp_path, tape_barcode: str, mount: Path):
    mount.mkdir(parents=True, exist_ok=True)
    db.initialize_database(config)
    with closing(db.connect(config)) as conn:
        with conn:
            conn.execute(
                "INSERT INTO tapes (barcode, current_location, state) VALUES (?, ?, ?)",
                (tape_barcode, "drive:drive0", "loaded"),
            )
            tape_id = conn.execute(
                "SELECT id FROM tapes WHERE barcode = ?", (tape_barcode,)
            ).fetchone()["id"]
            # initialize_database already inserted drive0 from config; just update it.
            conn.execute(
                """
                UPDATE drives
                SET mount_path = ?, loaded_tape_id = ?, state = 'full'
                WHERE id = 'drive0'
                """,
                (str(mount), tape_id),
            )
    return tape_id


def _make_queued_write_job(config, tmp_path, tape_barcode: str, files: list[tuple]):
    """Stage files and return the queued write_archive job."""
    src = tmp_path / "source"
    plan = _make_plan(src, tape_barcode, files)
    db.initialize_database(config)
    jobs = archive.stage_games_archive(config, plan)
    return jobs[0]


def test_write_archive_produces_files_on_tape(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)

    job = _make_queued_write_job(
        config, tmp_path, "385182L5",
        [("Nintendo/mario.zip", b"mario data"), ("PC/quake.zip", b"quake data")],
    )

    # Patch _find_tape_mount_path to return the local directory.
    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        result = archive.write_staged_archive(config, job)

    assert result["state"] == "complete"
    assert (mount / "games" / "Nintendo" / "mario.zip").is_file()
    assert (mount / "games" / "PC" / "quake.zip").is_file()


def test_write_archive_creates_manifests(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)

    job = _make_queued_write_job(
        config, tmp_path, "385182L5",
        [("game.zip", b"game content")],
    )

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        archive.write_staged_archive(config, job)

    assert (mount / "TAPE-MANIFEST.json").is_file()
    manifest = json.loads((mount / "TAPE-MANIFEST.json").read_text())
    assert manifest["tape_barcode"] == "385182L5"
    assert manifest["file_count"] == 1

    assert (mount / "TAPE-MANIFEST.csv").is_file()
    assert (mount / "TAPE-CHECKSUMS.sha256").is_file()
    assert (mount / "README-THIS-TAPE.txt").is_file()


def test_write_archive_updates_catalog(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)

    job = _make_queued_write_job(
        config, tmp_path, "385182L5",
        [("game.zip", b"catalog content")],
    )

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        archive.write_staged_archive(config, job)

    files = db.list_files(config, tape_barcode="385182L5")
    paths = {f["path"] for f in files}
    assert "games/game.zip" in paths
    file_row = next(f for f in files if f["path"] == "games/game.zip")
    assert file_row["state"] == "verified"
    assert file_row["checksum_sha256"]


def test_write_archive_not_mounted_sets_waiting(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)

    job = _make_queued_write_job(
        config, tmp_path, "385182L5",
        [("game.zip", b"data")],
    )

    # _find_tape_mount_path returns None → tape not mounted.
    with patch.object(archive, "_find_tape_mount_path", return_value=None):
        with pytest.raises(ArchiveError, match="not mounted"):
            archive.write_staged_archive(config, job)

    updated = db.get_job_by_id(config, job["id"])
    assert updated["state"] == "waiting_for_mount"


def test_write_archive_records_partial_progress_after_failure(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)

    job = _make_queued_write_job(
        config,
        tmp_path,
        "385182L5",
        [("a.bin", b"alpha"), ("b.bin", b"bravo")],
    )

    real_copy2 = archive.shutil.copy2

    def flaky_copy2(source, destination, *args, **kwargs):
        if Path(source).name == "b.bin":
            raise OSError("simulated write interruption")
        return real_copy2(source, destination, *args, **kwargs)

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        with patch("tapelib.archive.shutil.copy2", side_effect=flaky_copy2):
            with pytest.raises(OSError, match="simulated write interruption"):
                archive.write_staged_archive(config, job)

    updated = db.get_job_by_id(config, job["id"])
    assert updated["state"] == "failed"
    assert (mount / "games" / "a.bin").is_file()
    assert not (mount / "games" / "b.bin").exists()

    files = db.list_files(config, tape_barcode="385182L5")
    assert {file_row["path"] for file_row in files} == {"games/a.bin"}

    staged_files = job["source"]["files"]
    assert not Path(staged_files[0]["staging_path"]).exists()
    assert Path(staged_files[1]["staging_path"]).is_file()

    with closing(db.connect(config)) as conn:
        states = {
            row["cache_path"]: row["state"]
            for row in conn.execute(
                "SELECT cache_path, state FROM cache_entries WHERE job_id = ? ORDER BY cache_path",
                (job["id"],),
            ).fetchall()
        }
    assert states[staged_files[0]["staging_path"]] == "consumed"
    assert states[staged_files[1]["staging_path"]] == "staged"


def test_stage_skips_already_written_files_after_partial_failure(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)
    src = tmp_path / "source"
    plan = _make_plan(
        src,
        "385182L5",
        [("a.bin", b"alpha"), ("b.bin", b"bravo")],
    )
    job = archive.stage_games_archive(config, plan)[0]

    real_copy2 = archive.shutil.copy2

    def flaky_copy2(source, destination, *args, **kwargs):
        if Path(source).name == "b.bin":
            raise OSError("simulated write interruption")
        return real_copy2(source, destination, *args, **kwargs)

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        with patch("tapelib.archive.shutil.copy2", side_effect=flaky_copy2):
            with pytest.raises(OSError):
                archive.write_staged_archive(config, job)

    next_jobs = archive.stage_games_archive(config, plan, max_staged_bytes=10)
    assert len(next_jobs) == 1
    assert [file_row["logical_path"] for file_row in next_jobs[0]["source"]["files"]] == [
        "b.bin"
    ]


def test_write_archive_resume_skips_existing_files(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)

    job = _make_queued_write_job(
        config,
        tmp_path,
        "385182L5",
        [("a.bin", b"alpha"), ("b.bin", b"bravo")],
    )

    real_copy2 = archive.shutil.copy2

    def flaky_copy2(source, destination, *args, **kwargs):
        if Path(source).name == "b.bin":
            raise OSError("simulated write interruption")
        return real_copy2(source, destination, *args, **kwargs)

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        with patch("tapelib.archive.shutil.copy2", side_effect=flaky_copy2):
            with pytest.raises(OSError):
                archive.write_staged_archive(config, job)

    resumed_job = db.get_job_by_id(config, job["id"])
    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        result = archive.write_staged_archive(config, resumed_job, resume=True)

    assert result["state"] == "complete"
    assert (mount / "games" / "a.bin").is_file()
    assert (mount / "games" / "b.bin").is_file()

    events = db.list_job_events(config, job_id=job["id"], limit=50)
    assert any(event["event_type"] == "file_already_present" for event in events)

    with closing(db.connect(config)) as conn:
        states = {
            row["state"]
            for row in conn.execute(
                "SELECT state FROM cache_entries WHERE job_id = ?",
                (job["id"],),
            ).fetchall()
        }
    assert states == {"consumed"}


def test_write_archive_resume_validates_against_library_catalog(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)

    job = _make_queued_write_job(
        config,
        tmp_path,
        "385182L5",
        [("a.bin", b"alpha"), ("b.bin", b"bravo")],
    )

    real_copy2 = archive.shutil.copy2

    def flaky_copy2(source, destination, *args, **kwargs):
        if Path(source).name == "b.bin":
            raise OSError("simulated write interruption")
        return real_copy2(source, destination, *args, **kwargs)

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        with patch("tapelib.archive.shutil.copy2", side_effect=flaky_copy2):
            with pytest.raises(OSError):
                archive.write_staged_archive(config, job)

    with closing(db.connect(config)) as conn:
        with conn:
            conn.execute(
                "UPDATE files SET checksum_sha256 = ? WHERE path = ?",
                ("deadbeef", "games/a.bin"),
            )

    resumed_job = db.get_job_by_id(config, job["id"])
    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        with pytest.raises(ArchiveError, match="Library catalog disagrees"):
            archive.write_staged_archive(config, resumed_job, resume=True)


def test_write_archive_records_bundle_preview_members(tmp_path):
    config = _config(tmp_path)
    config["archive"] = {
        "smallFileBundleMaxBytes": "10",
        "smallFileBundleTargetBytes": "32",
    }
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)
    src = tmp_path / "source"
    plan = _make_plan(
        src,
        "385182L5",
        [("games/a.bin", b"a" * 8), ("games/b.bin", b"b" * 8)],
    )
    job = archive.stage_games_archive(config, plan)[0]

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        archive.write_staged_archive(config, job)

    bundle_members = db.list_bundle_members(config, tape_barcode="385182L5")
    assert {row["member_path"] for row in bundle_members} == {
        "games/games/a.bin",
        "games/games/b.bin",
    }
    assert any(row["bundle_path"].endswith(".tar") for row in bundle_members)


def test_write_archive_wrong_job_type_raises(tmp_path):
    config = _config(tmp_path)
    db.initialize_database(config)
    job = db.create_job(config, "retrieve_files", source={}, target={})
    with pytest.raises(ArchiveError, match="write_archive"):
        archive.write_staged_archive(config, job)


def test_write_archive_refuses_overwrite(tmp_path):
    config = _config(tmp_path)
    mount = tmp_path / "drive0"
    _seed_tape_and_drive(config, tmp_path, "385182L5", mount)

    job = _make_queued_write_job(
        config, tmp_path, "385182L5",
        [("game.zip", b"original")],
    )

    # Pre-create the final path to trigger the overwrite check.
    (mount / "games").mkdir(parents=True, exist_ok=True)
    (mount / "games" / "game.zip").write_bytes(b"already here")

    with patch.object(archive, "_find_tape_mount_path", return_value=str(mount)):
        with pytest.raises(ArchiveError, match="already exists"):
            archive.write_staged_archive(config, job)

    # Job should be failed.
    updated = db.get_job_by_id(config, job["id"])
    assert updated["state"] == "failed"
