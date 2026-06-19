from __future__ import annotations

import argparse
import json
from contextlib import closing
from pathlib import Path

import pytest

from tapelib import cli, db
from tapelib.executor import ExecutionError


def _config(tmp_path: Path) -> dict:
    return {
        "stateDir": str(tmp_path / "state"),
        "database": {"path": str(tmp_path / "catalog.sqlite")},
        "library": {
            "changerDevice": "/dev/test-changer",
            "drives": [
                {
                    "name": "drive0",
                    "stDevice": "/dev/nst0",
                    "mountPath": str(tmp_path / "drive0"),
                },
                {
                    "name": "drive1",
                    "stDevice": "/dev/nst1",
                    "mountPath": str(tmp_path / "drive1"),
                },
            ],
            "allowedGenerations": ["L5"],
        },
    }


def _seed_mounted_tape(config: dict, barcode: str, mount_path: Path, drive: str) -> None:
    mount_path.mkdir(parents=True, exist_ok=True)
    db.initialize_database(config)
    with closing(db.connect(config)) as conn:
        with conn:
            conn.execute(
                "INSERT INTO tapes (barcode, generation, current_location, state) VALUES (?, ?, ?, ?)",
                (barcode, "L5", f"drive:{drive}", "loaded"),
            )
            tape_id = conn.execute(
                "SELECT id FROM tapes WHERE barcode = ?", (barcode,)
            ).fetchone()["id"]
            conn.execute(
                "UPDATE drives SET mount_path = ?, loaded_tape_id = ?, state = 'full' WHERE id = ?",
                (str(mount_path), tape_id, drive),
            )
            conn.execute(
                """
                INSERT INTO files (tape_id, path, size_bytes, checksum_sha256, state, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    tape_id,
                    "games/test.bin",
                    4,
                    None,
                    "indexed",
                    "2026-04-29T00:00:00Z",
                ),
            )
    (mount_path / "games").mkdir(parents=True, exist_ok=True)
    (mount_path / "games" / "test.bin").write_bytes(b"data")


def test_verify_uses_single_mounted_tape_when_unspecified(tmp_path, monkeypatch):
    config = _config(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    _seed_mounted_tape(config, "385182L5", tmp_path / "drive0", "drive0")

    monkeypatch.setattr(cli, "_is_mounted", lambda path: path == str(tmp_path / "drive0"))

    args = argparse.Namespace(config=str(config_path), tape=None, mode="metadata")
    assert cli._command_verify(args) == 0

    status = json.loads(
        (tmp_path / "state" / "status" / "verify.json").read_text(encoding="utf-8")
    )
    assert status["tape_barcode"] == "385182L5"
    assert status["checked_files"] == 1
    assert status["verified_files"] == 1
    assert len(status["tapes"]) == 1


def test_verify_without_mounted_tapes_requires_target(tmp_path, monkeypatch):
    config = _config(tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    db.initialize_database(config)
    monkeypatch.setattr(cli, "_is_mounted", lambda _path: False)

    args = argparse.Namespace(config=str(config_path), tape=None, mode="metadata")
    with pytest.raises(ExecutionError, match="No mounted allowed tape is available"):
        cli._command_verify(args)


def test_operator_console_payload_surfaces_cache_tapes_jobs_and_warnings(tmp_path):
    config = _config(tmp_path)
    config["cache"] = {"path": str(tmp_path / "cache")}
    (tmp_path / "cache").mkdir()
    _seed_mounted_tape(config, "385182L5", tmp_path / "drive0", "drive0")

    with closing(db.connect(config)) as conn:
        with conn:
            conn.execute("UPDATE files SET state = 'read_error'")
            job = db.create_job_with_connection(
                conn,
                "retrieve_files",
                state="queued",
                source={
                    "kind": "test",
                    "files": [
                        {"path": "a", "staging_path": "/cache/a"},
                        {"path": "b", "staging_path": "/cache/b"},
                    ],
                },
                target={"destination_root": str(tmp_path / "out")},
            )
            db.transition_job(
                conn,
                job["id"],
                "failed",
                event_type="job_failed",
                message="simulated failure",
                last_error="simulated failure",
            )

    payload = cli._operator_console_payload(config)

    assert payload["cache"]["exists"] is True
    assert payload["tapes"][0]["barcode"] == "385182L5"
    assert payload["drives"][0]["id"] == "drive0"
    warning_kinds = {warning["kind"] for warning in payload["warnings"]["warnings"]}
    assert {"job", "file"}.issubset(warning_kinds)
    assert any(job_row["state"] == "failed" for job_row in payload["jobs"])
    failed_job = next(job_row for job_row in payload["jobs"] if job_row["id"] == job["id"])
    assert failed_job["source"]["file_count"] == 2
    assert "files" not in failed_job["source"]
    assert "staging_path" not in json.dumps(payload)


def test_operator_console_payload_handles_unreadable_cache_path(tmp_path, monkeypatch):
    config = _config(tmp_path)
    denied_path = tmp_path / "cache"
    config["cache"] = {"path": str(denied_path)}

    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        if path == denied_path:
            raise PermissionError("simulated denial")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", fake_exists)

    payload = cli._operator_console_payload(config)

    assert payload["cache"]["exists"] is False
    assert "simulated denial" in payload["cache"]["error"]
    assert any(
        warning["kind"] == "cache" and "simulated denial" in warning["message"]
        for warning in payload["warnings"]["warnings"]
    )


def test_filesystem_smoke_payload_covers_virtual_surface(tmp_path):
    mount = tmp_path / "tapelib"
    for directory in [
        "browse/TAPE001L5",
        "readable/TAPE001L5",
        "jobs/active",
        "jobs/complete",
        "jobs/failed",
        "jobs/queued",
        "jobs/waiting",
        "system/drives",
        "thumbnails/by-filetype",
        "thumbnails/cached",
        "write/inbox-cached",
        "write/inbox-direct",
    ]:
        (mount / directory).mkdir(parents=True, exist_ok=True)
    for relative in [
        "README.txt",
        "browse/TAPE001L5/README.txt",
        "readable/TAPE001L5/README.txt",
        "jobs/jobs.json",
        "jobs/journal.json",
        "system/config.json",
        "system/status.json",
        "system/inventory.json",
        "system/drives/drive0.json",
        "thumbnails/README.txt",
        "thumbnails/cached/README.txt",
        "thumbnails/by-filetype/folder.png",
        "thumbnails/by-filetype/iso.png",
        "thumbnails/by-filetype/unknown.png",
        "thumbnails/by-filetype/zip.png",
        "write/README.txt",
        "write/inbox-cached/README.txt",
        "write/inbox-direct/README.txt",
    ]:
        path = mount / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    config = _config(tmp_path)
    payload = cli._filesystem_smoke_payload(
        config,
        mount_point=mount,
        fast_budget_ms=1000,
    )

    labels = {result["label"] for result in payload["results"]}
    assert payload["ok"] is True
    assert "root list" in labels
    assert "system list" in labels
    assert "browse tape list" in labels
    assert "system drive read drive0.json" in labels


def _seed_game_write_job(
    config: dict,
    barcode: str,
    *,
    state: str,
    file_count: int,
    size_bytes: int,
) -> dict:
    db.initialize_database(config)
    files = [
        {
            "logical_path": f"unit/file-{index}.zip",
            "source_path": f"/games/source/file-{index}.zip",
            "staging_path": f"/cache/{barcode}/file-{index}.zip",
            "size_bytes": size_bytes // file_count,
        }
        for index in range(file_count)
    ]
    with closing(db.connect(config)) as conn:
        with conn:
            tape_id = db.get_or_create_tape(conn, barcode)
            return db.create_job_with_connection(
                conn,
                "write_archive",
                state=state,
                source={
                    "batch_bytes": size_bytes,
                    "files": files,
                    "staging_dir": f"/cache/{barcode}",
                },
                target={"namespace_prefix": "games", "tape_barcode": barcode},
                required_bytes=size_bytes,
                assigned_tape_id=tape_id,
            )


def test_games_backup_status_reports_active_state_and_plan(
    tmp_path, monkeypatch, capsys
):
    config = _config(tmp_path)
    config["games"] = {
        "namespacePrefix": "/games",
        "sourceRoots": ["/games/incoming"],
        "selectedTapes": ["385182L5", "430550L5"],
        "tapeCapacityBytes": 1000,
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    _seed_game_write_job(
        config,
        "385182L5",
        state="complete",
        file_count=3,
        size_bytes=3 * 1024**3,
    )
    queued = _seed_game_write_job(
        config,
        "385182L5",
        state="queued",
        file_count=5,
        size_bytes=5 * 1024**3,
    )

    monkeypatch.setattr(
        cli,
        "_plan_game_backup",
        lambda _config: {
            "selected_tapes": ["385182L5", "430550L5"],
            "assignments": [
                {
                    "tape": "385182L5",
                    "unit_path": "a",
                    "size_bytes": 3 * 1024**3,
                    "files": [{}, {}, {}],
                },
                {
                    "tape": "430550L5",
                    "unit_path": "b",
                    "size_bytes": 7 * 1024**3,
                    "files": [{}],
                },
            ],
        },
    )

    args = argparse.Namespace(
        config=str(config_path), json=False, plan=True, no_plan=False
    )
    assert cli._command_games_backup_status(args) == 0

    output = capsys.readouterr().out
    assert "Game library backup active: NO" in output
    assert "Tape actually written so far: 385182L5" in output
    assert "Completed game archive writes: 1 batches" in output
    assert "Written: 3 game files, about 3.00 GiB" in output
    assert "Queued next write: 5 files, about 5.00 GiB, also for 385182L5" in output
    assert f"Next job: {queued['id']} (queued)" in output
    assert "games-backup-run-next --resume" in output
    assert f"write-archive --job-id {queued['id']} --resume" in output
    assert "The full current plan uses 2 tapes:" in output
    assert "430550L5" in output


def test_games_backup_status_skips_plan_scan_by_default(
    tmp_path, monkeypatch, capsys
):
    config = _config(tmp_path)
    config["games"] = {"namespacePrefix": "/games"}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    _seed_game_write_job(
        config,
        "385182L5",
        state="complete",
        file_count=3,
        size_bytes=3 * 1024**3,
    )

    monkeypatch.setattr(
        cli,
        "_plan_game_backup",
        lambda _config: pytest.fail("default status should not scan sources"),
    )

    args = argparse.Namespace(
        config=str(config_path), json=False, plan=False, no_plan=False
    )
    assert cli._command_games_backup_status(args) == 0

    output = capsys.readouterr().out
    assert "Written: 3 game files, about 3.00 GiB" in output
    assert "The full current plan uses" not in output


def test_plan_games_backup_packs_later_units_into_earlier_tape_space(tmp_path):
    source_root = tmp_path / "games"
    for unit_name, size in [
        ("a", 8),
        ("b", 7),
        ("c", 2),
        ("d", 2),
    ]:
        unit_dir = source_root / unit_name
        unit_dir.mkdir(parents=True)
        (unit_dir / "game.bin").write_bytes(b"x" * size)

    config = _config(tmp_path)
    config["games"] = {
        "namespacePrefix": "/games",
        "sourceRoots": [str(source_root)],
        "selectedTapes": ["385182L5", "430550L5", "383685L5"],
        "tapeCapacityBytes": 10,
    }

    plan = cli._plan_game_backup(config)

    by_tape = {
        tape["tape"]: {unit["unit_path"] for unit in tape["units"]}
        for tape in plan["tapes"]
    }
    assert by_tape == {
        "385182L5": {"a", "c"},
        "430550L5": {"b", "d"},
    }


def test_games_backup_run_next_uses_oldest_runnable_job(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path)
    config["games"] = {"namespacePrefix": "/games"}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    first = _seed_game_write_job(
        config, "385182L5", state="queued", file_count=1, size_bytes=1024
    )
    _seed_game_write_job(
        config, "385182L5", state="queued", file_count=2, size_bytes=2048
    )

    observed = {}

    def fake_write(_config, job, *, resume=False):
        observed["job_id"] = job["id"]
        observed["resume"] = resume
        return {**job, "state": "complete"}

    monkeypatch.setattr("tapelib.archive.write_staged_archive", fake_write)

    args = argparse.Namespace(config=str(config_path), resume=False, json=False)
    assert cli._command_games_backup_run_next(args) == 0

    assert observed == {"job_id": first["id"], "resume": False}
    assert "Completed game archive write" in capsys.readouterr().out


def test_games_backup_run_next_resume_uses_needs_operator_job(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    config["games"] = {"namespacePrefix": "/games"}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    job = _seed_game_write_job(
        config, "385182L5", state="needs_operator", file_count=1, size_bytes=1024
    )

    observed = {}

    def fake_write(_config, selected_job, *, resume=False):
        observed["job_id"] = selected_job["id"]
        observed["resume"] = resume
        return {**selected_job, "state": "complete"}

    monkeypatch.setattr("tapelib.archive.write_staged_archive", fake_write)

    args = argparse.Namespace(config=str(config_path), resume=True, json=False)
    assert cli._command_games_backup_run_next(args) == 0

    assert observed == {"job_id": job["id"], "resume": True}


def test_files_payload_can_filter_by_tape(tmp_path):
    config = _config(tmp_path)
    _seed_mounted_tape(config, "385182L5", tmp_path / "drive0", "drive0")

    payload = cli._files_payload(config, tape_barcode="385182L5", limit=10)

    assert payload["total"] == 1
    assert payload["files"][0]["path"] == "games/test.bin"


def test_operator_console_html_uses_console_api():
    html = cli._operator_console_html()
    assert "/api/console" in html
    assert "<h1>tapelib</h1>" in html


def test_web_retrieve_action_queues_job(tmp_path):
    config = _config(tmp_path)
    _seed_mounted_tape(config, "385182L5", tmp_path / "drive0", "drive0")

    result = cli._web_action(
        config,
        "retrieve",
        {
            "files": ["385182L5:/games/test.bin"],
            "dest": str(tmp_path / "restore"),
        },
    )

    assert result["action"] == "retrieve"
    assert result["job"]["type"] == "retrieve_files"
    assert result["job"]["state"] == "queued"


def test_web_cancel_action_requires_confirmation(tmp_path):
    config = _config(tmp_path)
    _seed_mounted_tape(config, "385182L5", tmp_path / "drive0", "drive0")
    job = db.create_job(config, "retrieve_files", source={}, target={})

    with pytest.raises(ExecutionError, match="confirm"):
        cli._web_action(config, "cancel", {"job_id": job["id"]})

    result = cli._web_action(
        config,
        "cancel",
        {"job_id": job["id"], "confirm": "cancel"},
    )
    assert result["job"]["state"] == "cancelled"


def test_web_promote_ingest_action_requires_confirmation(tmp_path):
    config = _config(tmp_path)
    config["cache"] = {"path": str(tmp_path / "cache")}
    cache_file = tmp_path / "cache" / "write-inbox" / "inbox-cached" / "ready" / "new.bin"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_bytes(b"payload")
    db.initialize_database(config)
    with closing(db.connect(config)) as conn:
        with conn:
            ingest_job = db.create_job_with_connection(
                conn,
                "ingest_cached_files",
                state="queued",
                source={
                    "kind": "fuse_inbox_cached",
                    "relative_path": "new.bin",
                    "cache_path": str(cache_file),
                },
                target={"namespace_prefix": "/incoming"},
            )

    with pytest.raises(ExecutionError, match="confirm"):
        cli._web_action(
            config,
            "promote-ingest",
            {"job_id": ingest_job["id"], "tape": "385182L5"},
        )

    result = cli._web_action(
        config,
        "promote-ingest",
        {
            "job_id": ingest_job["id"],
            "tape": "385182L5",
            "confirm": "promote-ingest",
        },
    )

    assert result["write_job"]["type"] == "write_archive"
    assert result["ingest_job"]["state"] == "complete"


def test_web_index_tape_action_requires_confirmation_and_mounted_tape(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    _seed_mounted_tape(config, "385182L5", tmp_path / "drive0", "drive0")
    monkeypatch.setattr(cli, "_is_mounted", lambda path: path == str(tmp_path / "drive0"))

    with pytest.raises(ExecutionError, match="confirm"):
        cli._web_action(config, "index-tape", {"target": "drive0"})

    result = cli._web_action(
        config,
        "index-tape",
        {"target": "drive0", "confirm": "index-tape"},
    )

    assert result["tape_barcode"] == "385182L5"
    assert result["drive"] == "drive0"
    assert result["index"]["indexed_count"] == 1


def test_web_verify_action_requires_confirmation_and_writes_status(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    _seed_mounted_tape(config, "385182L5", tmp_path / "drive0", "drive0")
    monkeypatch.setattr(cli, "_is_mounted", lambda path: path == str(tmp_path / "drive0"))

    with pytest.raises(ExecutionError, match="confirm"):
        cli._web_action(config, "verify", {"target": "drive0"})

    result = cli._web_action(
        config,
        "verify",
        {"target": "drive0", "mode": "metadata", "confirm": "verify"},
    )

    status = json.loads(
        (tmp_path / "state" / "status" / "verify.json").read_text(encoding="utf-8")
    )
    assert result["verification"]["tape_barcode"] == "385182L5"
    assert result["verification"]["verified_files"] == 1
    assert status["checked_files"] == 1


def test_web_hardware_actions_require_confirmation_and_call_executor(
    tmp_path, monkeypatch
):
    config = _config(tmp_path)
    calls = []

    def fake_load_tape(_config, barcode, drive):
        calls.append(("load", barcode, drive))
        return {"id": "load-job", "type": "load_tape"}

    def fake_unload_tape(_config, drive, *, destination_slot=None):
        calls.append(("unload", drive, destination_slot))
        return {"id": "unload-job", "type": "unload_tape"}

    def fake_mount_ltfs(_config, drive, *, read_only=True):
        calls.append(("mount", drive, read_only))
        return {"id": "mount-job", "type": "mount_ltfs"}

    def fake_unmount_ltfs(_config, drive):
        calls.append(("unmount", drive))
        return {"id": "unmount-job", "type": "unmount_ltfs"}

    monkeypatch.setattr(cli.executor, "load_tape", fake_load_tape)
    monkeypatch.setattr(cli.executor, "unload_tape", fake_unload_tape)
    monkeypatch.setattr(cli.executor, "mount_ltfs", fake_mount_ltfs)
    monkeypatch.setattr(cli.executor, "unmount_ltfs", fake_unmount_ltfs)

    with pytest.raises(ExecutionError, match="confirm"):
        cli._web_action(config, "load-tape", {"barcode": "385182L5", "drive": "drive0"})

    assert cli._web_action(
        config,
        "load-tape",
        {"barcode": "385182L5", "drive": "drive0", "confirm": "load-tape"},
    )["job"]["type"] == "load_tape"
    assert cli._web_action(
        config,
        "unload-tape",
        {"drive": "drive0", "slot": "12", "confirm": "unload-tape"},
    )["job"]["type"] == "unload_tape"
    assert cli._web_action(
        config,
        "mount-ltfs",
        {"drive": "drive1", "read_write": True, "confirm": "mount-ltfs"},
    )["job"]["type"] == "mount_ltfs"
    assert cli._web_action(
        config,
        "unmount-ltfs",
        {"drive": "drive1", "confirm": "unmount-ltfs"},
    )["job"]["type"] == "unmount_ltfs"

    assert calls == [
        ("load", "385182L5", "drive0"),
        ("unload", "drive0", 12),
        ("mount", "drive1", False),
        ("unmount", "drive1"),
    ]
