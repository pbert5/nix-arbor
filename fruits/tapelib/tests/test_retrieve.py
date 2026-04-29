from __future__ import annotations

import json
from contextlib import closing
from types import SimpleNamespace

import pytest

from tapelib import cli, db, executor, job_status


def _config(tmp_path):
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
                }
            ],
        },
    }


def _seed_catalog(config):
    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        with connection:
            connection.execute(
                """
                INSERT INTO tapes (barcode, generation, current_location, state)
                VALUES ('TAPE001L5', 'L5', 'slot:1', 'in_library')
                """
            )
            connection.execute(
                """
                INSERT INTO tapes (barcode, generation, current_location, state)
                VALUES ('TAPE002L5', 'L5', 'drive:drive0', 'loaded')
                """
            )
            tape1_id = connection.execute(
                "SELECT id FROM tapes WHERE barcode = 'TAPE001L5'"
            ).fetchone()["id"]
            tape2_id = connection.execute(
                "SELECT id FROM tapes WHERE barcode = 'TAPE002L5'"
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO files (tape_id, path, size_bytes, state)
                VALUES (?, 'games/a.zip', 100, 'indexed')
                """,
                (tape1_id,),
            )
            connection.execute(
                """
                INSERT INTO files (tape_id, path, size_bytes, state)
                VALUES (?, 'games/b.zip', 200, 'indexed')
                """,
                (tape2_id,),
            )
            connection.execute(
                """
                UPDATE drives
                SET loaded_tape_id = ?, state = 'full'
                WHERE id = 'drive0'
                """,
                (tape2_id,),
            )


def _manifest(tmp_path, files):
    path = tmp_path / "retrieve.json"
    path.write_text(json.dumps({"files": files}), encoding="utf-8")
    return path


def test_retrieve_plan_groups_loaded_tape_first_and_preserves_paths(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    manifest = _manifest(
        tmp_path,
        [
            "TAPE001L5:/games/a.zip",
            {"tape_barcode": "TAPE002L5", "path": "games/b.zip"},
        ],
    )

    plan = cli._build_retrieve_plan(config, manifest, tmp_path / "out")

    assert plan["layout"] == "preserve_tape_and_archive_path"
    assert plan["total_bytes"] == 300
    assert [group["tape_barcode"] for group in plan["groups"]] == [
        "TAPE002L5",
        "TAPE001L5",
    ]
    assert plan["files"][0]["destination_path"].endswith(
        "out/TAPE001L5/games/a.zip"
    )


def test_retrieve_rejects_unknown_catalog_entry(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    manifest = _manifest(tmp_path, ["TAPE001L5:/missing.zip"])

    with pytest.raises(executor.ExecutionError):
        cli._build_retrieve_plan(config, manifest, tmp_path / "out")


def test_retrieve_jobs_coalesce_and_cancel(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    manifest = _manifest(tmp_path, ["TAPE001L5:/games/a.zip"])
    plan = cli._build_retrieve_plan(config, manifest, tmp_path / "out")

    first = cli._queue_retrieve_plan(config, plan)
    second = cli._queue_retrieve_plan(config, plan)

    assert first["coalesced"] is False
    assert second["coalesced"] is True
    assert first["job"]["id"] == second["job"]["id"]

    args = SimpleNamespace(
        config=_config_path(tmp_path, config), job_id=first["job"]["id"]
    )
    assert cli._command_cancel(args) == 0
    cancelled = db.get_job_by_id(config, first["job"]["id"])
    assert cancelled["state"] == "cancelled"


def test_run_queue_copies_from_mounted_ltfs_path(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)
    source = tmp_path / "drive0" / "games" / "b.zip"
    source.parent.mkdir(parents=True)
    source.write_text("payload", encoding="utf-8")
    monkeypatch.setattr(cli, "_is_mounted", lambda _path: True)

    manifest = _manifest(tmp_path, ["TAPE002L5:/games/b.zip"])
    plan = cli._build_retrieve_plan(config, manifest, tmp_path / "out")
    queued = cli._queue_retrieve_plan(config, plan)

    result = cli._run_queue_once(config)

    destination = tmp_path / "out" / "TAPE002L5" / "games" / "b.zip"
    assert result["ran"] is True
    assert result["state"] == "complete"
    assert result["job"]["id"] == queued["job"]["id"]
    assert result["copied_files"][0]["destination_path"] == str(destination)
    assert destination.read_text(encoding="utf-8") == "payload"
    assert db.get_job_by_id(config, queued["job"]["id"])["state"] == "complete"
    status = job_status.snapshot(config, queued["job"]["id"])
    assert status["progress_percent"] == 100
    assert status["copied_file_count"] == 1
    assert status["copied_bytes"] == 200


def test_run_queue_blocks_when_required_tape_is_not_mounted(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)
    monkeypatch.setattr(cli, "_is_mounted", lambda _path: True)
    manifest = _manifest(tmp_path, ["TAPE001L5:/games/a.zip"])
    plan = cli._build_retrieve_plan(config, manifest, tmp_path / "out")
    queued = cli._queue_retrieve_plan(config, plan)

    result = cli._run_queue_once(config)

    assert result["ran"] is False
    assert result["state"] == "waiting_for_mount"
    assert result["blocked_tapes"] == ["TAPE001L5"]
    assert not (tmp_path / "out").exists()
    assert db.get_job_by_id(config, queued["job"]["id"])["state"] == "waiting_for_mount"
    status = job_status.snapshot(config, queued["job"]["id"])
    assert status["bucket"] == "waiting"
    assert status["blocked_tapes"] == ["TAPE001L5"]
    assert status["progress_percent"] == 0

    coalesced = cli._queue_retrieve_plan(config, plan)
    assert coalesced["coalesced"] is True
    assert coalesced["job"]["id"] == queued["job"]["id"]

    args = SimpleNamespace(
        config=_config_path(tmp_path, config), job_id=queued["job"]["id"]
    )
    assert cli._command_cancel(args) == 0
    assert db.get_job_by_id(config, queued["job"]["id"])["state"] == "cancelled"


def test_job_status_command_prints_snapshot(tmp_path, monkeypatch, capsys):
    config = _config(tmp_path)
    _seed_catalog(config)
    source = tmp_path / "drive0" / "games" / "b.zip"
    source.parent.mkdir(parents=True)
    source.write_text("payload", encoding="utf-8")
    monkeypatch.setattr(cli, "_is_mounted", lambda _path: True)

    manifest = _manifest(tmp_path, ["TAPE002L5:/games/b.zip"])
    plan = cli._build_retrieve_plan(config, manifest, tmp_path / "out")
    queued = cli._queue_retrieve_plan(config, plan)
    cli._run_queue_once(config)

    args = SimpleNamespace(
        config=_config_path(tmp_path, config),
        job_id=queued["job"]["id"],
        event_limit=20,
    )
    assert cli._command_job_status(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["job_id"] == queued["job"]["id"]
    assert payload["state"] == "complete"
    assert payload["progress_percent"] == 100


def test_run_queue_fails_without_overwriting_existing_destination(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)
    source = tmp_path / "drive0" / "games" / "b.zip"
    source.parent.mkdir(parents=True)
    source.write_text("new payload", encoding="utf-8")
    destination = tmp_path / "out" / "TAPE002L5" / "games" / "b.zip"
    destination.parent.mkdir(parents=True)
    destination.write_text("existing payload", encoding="utf-8")
    monkeypatch.setattr(cli, "_is_mounted", lambda _path: True)

    manifest = _manifest(tmp_path, ["TAPE002L5:/games/b.zip"])
    plan = cli._build_retrieve_plan(config, manifest, tmp_path / "out")
    queued = cli._queue_retrieve_plan(config, plan)

    result = cli._run_queue_once(config)

    assert result["ran"] is True
    assert result["state"] == "failed"
    assert "will not be overwritten" in result["message"]
    assert destination.read_text(encoding="utf-8") == "existing payload"
    failed = db.get_job_by_id(config, queued["job"]["id"])
    assert failed["state"] == "failed"
    assert "will not be overwritten" in failed["last_error"]


def test_run_queue_fails_when_mounted_source_is_missing(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)
    monkeypatch.setattr(cli, "_is_mounted", lambda _path: True)
    manifest = _manifest(tmp_path, ["TAPE002L5:/games/b.zip"])
    plan = cli._build_retrieve_plan(config, manifest, tmp_path / "out")
    queued = cli._queue_retrieve_plan(config, plan)

    result = cli._run_queue_once(config)

    assert result["ran"] is True
    assert result["state"] == "failed"
    assert "Mounted source file is missing" in result["message"]
    failed = db.get_job_by_id(config, queued["job"]["id"])
    assert failed["state"] == "failed"
    assert "Mounted source file is missing" in failed["last_error"]


@pytest.mark.parametrize("state", ["running", "waiting_for_changer"])
def test_hardware_facing_job_cannot_be_cancelled(tmp_path, state):
    config = _config(tmp_path)
    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        with connection:
            job = db.create_job_with_connection(
                connection,
                "retrieve_files",
                state=state,
                source={"files": []},
                target={"destination_root": str(tmp_path / "out")},
            )

    args = SimpleNamespace(config=_config_path(tmp_path, config), job_id=job["id"])
    with pytest.raises(executor.ExecutionError):
        cli._command_cancel(args)


def _config_path(tmp_path, config):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return str(path)
