from __future__ import annotations

import errno
import json
from contextlib import closing
from types import SimpleNamespace

import pytest
from fuse import FuseOSError

from tapelib import db, fuse_fs


def _config(tmp_path):
    return {
        "stateDir": str(tmp_path / "state"),
        "database": {"path": str(tmp_path / "catalog.sqlite")},
        "fuse": {"user": "missing-user", "group": "missing-group"},
        "games": {"selectedTapes": []},
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
            tape_id = connection.execute(
                "SELECT id FROM tapes WHERE barcode = 'TAPE001L5'"
            ).fetchone()["id"]
            connection.execute(
                """
                INSERT INTO files (tape_id, path, size_bytes, state)
                VALUES (?, 'games/foo.zip', 1234, 'indexed')
                """,
                (tape_id,),
            )


def test_browse_layout_and_metadata_do_not_touch_hardware(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)
    monkeypatch.setattr(
        fuse_fs.hardware,
        "read_changer_inventory",
        lambda _device: pytest.fail("browse touched changer inventory"),
    )

    fs = fuse_fs.TapelibFuse(config)

    assert "browse" in fs.readdir("/", None)
    assert "TAPE001L5" in fs.readdir("/browse", None)
    assert "foo.zip" in fs.readdir("/browse/TAPE001L5/games", None)
    assert fs.getattr("/browse/TAPE001L5/games/foo.zip")["st_size"] == 1234

    with pytest.raises(FuseOSError) as exc:
        fs.open("/browse/TAPE001L5/games/foo.zip", 0)
    assert exc.value.errno == errno.EACCES

    with pytest.raises(FuseOSError) as exc:
        fs.read("/browse/TAPE001L5/games/foo.zip", 10, 0, None)
    assert exc.value.errno == errno.EACCES


def test_system_inventory_is_lazy_and_hardware_backed(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)
    calls = []

    def inventory(device):
        calls.append(device)
        return SimpleNamespace(as_dict=lambda: {"device": device, "drives": []})

    monkeypatch.setattr(fuse_fs.hardware, "read_changer_inventory", inventory)
    fs = fuse_fs.TapelibFuse(config)

    assert calls == []
    assert "inventory.json" in fs.readdir("/system", None)
    assert calls == []
    assert b"/dev/test-changer" in fs.read("/system/inventory.json", 4096, 0, None)
    assert calls == ["/dev/test-changer"]


def test_write_surface_is_read_only(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    fs = fuse_fs.TapelibFuse(config)

    with pytest.raises(FuseOSError) as exc:
        fs.create("/write/inbox-cached/foo.zip", 0o644)
    assert exc.value.errno == errno.EROFS


def test_waiting_job_has_progress_snapshot_file(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        with connection:
            job = db.create_job_with_connection(
                connection,
                "retrieve_files",
                state="waiting_for_mount",
                target={
                    "groups": [
                        {
                            "tape_barcode": "TAPE001L5",
                            "files": [
                                {
                                    "archive_path": "games/foo.zip",
                                    "destination_path": str(tmp_path / "out/foo.zip"),
                                    "size_bytes": 1234,
                                }
                            ],
                        }
                    ]
                },
                required_bytes=1234,
            )
            db.append_job_event(
                connection,
                job["id"],
                "retrieve_waiting_for_mount",
                "Retrieve job is waiting for all required tapes to be mounted.",
                {"blocked_tapes": ["TAPE001L5"]},
            )

    fs = fuse_fs.TapelibFuse(config)

    job_file = f"{job['id']}.json"
    assert job_file in fs.readdir("/jobs/waiting", None)
    payload = json.loads(
        fs.read(f"/jobs/waiting/{job_file}", 65536, 0, None).decode("utf-8")
    )
    assert payload["job_id"] == job["id"]
    assert payload["bucket"] == "waiting"
    assert payload["blocked_tapes"] == ["TAPE001L5"]
