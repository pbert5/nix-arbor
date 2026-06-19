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


def test_browse_readdir_uses_short_metadata_cache(tmp_path, monkeypatch):
    config = _config(tmp_path)
    config["fuse"] = {"metadataCacheSeconds": 30}
    _seed_catalog(config)
    calls = 0
    original_list_files = fuse_fs.db.list_files

    def counted_list_files(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original_list_files(*args, **kwargs)

    monkeypatch.setattr(fuse_fs.db, "list_files", counted_list_files)
    fs = fuse_fs.TapelibFuse(config)

    assert "TAPE001L5" in fs.readdir("/browse", None)
    assert "TAPE001L5" in fs.readdir("/browse", None)

    assert calls == 0


def test_deep_browse_missing_probe_does_not_build_catalog_tree(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)

    monkeypatch.setattr(
        fuse_fs.db,
        "list_files",
        lambda *args, **kwargs: pytest.fail("missing path probe built file map"),
    )
    monkeypatch.setattr(
        fuse_fs.db,
        "list_bundle_members",
        lambda *args, **kwargs: pytest.fail("missing path probe built bundle map"),
    )

    fs = fuse_fs.TapelibFuse(config)

    assert "foo.zip" in fs.readdir("/browse/TAPE001L5/games", None)
    with pytest.raises(FuseOSError) as exc:
        fs.getattr("/browse/TAPE001L5/.envrc")
    assert exc.value.errno == errno.ENOENT


def test_shallow_navigation_does_not_build_catalog_tree(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)
    calls = 0

    def counted_list_files(*args, **kwargs):
        nonlocal calls
        calls += 1
        pytest.fail("shallow navigation should not list catalog files")

    monkeypatch.setattr(fuse_fs.db, "list_files", counted_list_files)
    fs = fuse_fs.TapelibFuse(config)

    for path in [
        "/browse",
        "/jobs",
        "/readable",
        "/system",
        "/thumbnails",
        "/write",
        "/README.txt",
    ]:
        fs.getattr(path)

    assert "inventory.json" in fs.readdir("/system", None)
    for path in [
        "/system/drives",
        "/system/config.json",
        "/system/inventory.json",
        "/system/status.json",
    ]:
        fs.getattr(path)

    assert calls == 0


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
    assert fs.getattr("/system/inventory.json")["st_size"] > 0
    assert calls == []
    assert b"/dev/test-changer" in fs.read("/system/inventory.json", 4096, 0, None)
    assert calls == ["/dev/test-changer"]


def test_non_cached_write_surface_is_read_only(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    fs = fuse_fs.TapelibFuse(config)

    with pytest.raises(FuseOSError) as exc:
        fs.create("/write/inbox-direct/foo.zip", 0o644)
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


def test_job_summary_files_compact_large_file_lists(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        with connection:
            job = db.create_job_with_connection(
                connection,
                "write_archive",
                state="queued",
                source={
                    "files": [
                        {"logical_path": "games/a.zip", "staging_path": "/cache/a.zip"},
                        {"logical_path": "games/b.zip", "staging_path": "/cache/b.zip"},
                    ]
                },
                target={
                    "groups": [
                        {
                            "tape_barcode": "TAPE001L5",
                            "files": [{"archive_path": "games/a.zip"}],
                        }
                    ]
                },
            )

    fs = fuse_fs.TapelibFuse(config)

    all_jobs = json.loads(fs.read("/jobs/jobs.json", 65536, 0, None).decode("utf-8"))
    queued_jobs = json.loads(
        fs.read("/jobs/queued/jobs.json", 65536, 0, None).decode("utf-8")
    )
    snapshot = json.loads(
        fs.read(f"/jobs/queued/{job['id']}.json", 65536, 0, None).decode("utf-8")
    )

    summary = all_jobs["jobs"][0]
    queued_summary = queued_jobs["jobs"][0]
    assert summary["source"]["file_count"] == 2
    assert "files" not in summary["source"]
    assert summary["target"]["group_count"] == 1
    assert "groups" not in summary["target"]
    assert queued_summary == summary
    assert snapshot["job_id"] == job["id"]


def test_bundled_members_are_previewed_in_browse_and_readable(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    with closing(db.connect(config)) as connection:
        with connection:
            tape_id = connection.execute(
                "SELECT id FROM tapes WHERE barcode = 'TAPE001L5'"
            ).fetchone()["id"]
            db.upsert_bundle_members_with_connection(
                connection,
                tape_id,
                "games/_tapelib-bundles/bundle-0001.tar",
                [
                    {
                        "member_path": "games/bundled/foo.txt",
                        "size_bytes": 42,
                        "checksum_sha256": "abc123",
                    }
                ],
                indexed_at="2026-04-29T00:00:00Z",
            )

    fs = fuse_fs.TapelibFuse(config)

    assert "foo.txt" in fs.readdir("/browse/TAPE001L5/games/bundled", None)
    assert fs.getattr("/browse/TAPE001L5/games/bundled/foo.txt")["st_size"] == 42

    readable = json.loads(
        fs.read("/readable/TAPE001L5/games/bundled/foo.txt", 65536, 0, None).decode("utf-8")
    )
    assert readable["error"] == "bundled_retrieve_not_implemented"
    assert readable["bundle_path"] == "games/_tapelib-bundles/bundle-0001.tar"


def test_readable_file_read_queues_retrieve_without_touching_hardware(tmp_path, monkeypatch):
    config = _config(tmp_path)
    _seed_catalog(config)
    monkeypatch.setattr(
        fuse_fs.hardware,
        "read_changer_inventory",
        lambda _device: pytest.fail("readable queue touched changer inventory"),
    )
    fs = fuse_fs.TapelibFuse(config)

    payload = json.loads(
        fs.read("/readable/TAPE001L5/games/foo.zip", 65536, 0, None).decode("utf-8")
    )

    assert payload["cache_status"] == "queued"
    assert payload["tape"] == "TAPE001L5"
    assert payload["path"] == "games/foo.zip"
    assert payload["destination_path"].endswith(
        "restore-jobs/fuse-readable/TAPE001L5/games/foo.zip"
    )

    jobs = db.list_jobs(config)
    assert len(jobs) == 1
    assert jobs[0]["type"] == "retrieve_files"
    assert jobs[0]["state"] == "queued"
    assert jobs[0]["source"]["kind"] == "fuse_readable"
    assert jobs[0]["target"]["groups"][0]["tape_barcode"] == "TAPE001L5"


def test_readable_file_access_coalesces_existing_retrieve_job(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    fs = fuse_fs.TapelibFuse(config)

    first = json.loads(
        fs.read("/readable/TAPE001L5/games/foo.zip", 65536, 0, None).decode("utf-8")
    )
    second = json.loads(
        fs.read("/readable/TAPE001L5/games/foo.zip", 65536, 0, None).decode("utf-8")
    )

    assert second["coalesced"] is True
    assert second["job_id"] == first["job_id"]
    assert len(db.list_jobs(config)) == 1


def test_readable_file_serves_restored_cache_without_queueing(tmp_path):
    config = _config(tmp_path)
    _seed_catalog(config)
    cached = (
        tmp_path
        / "cache"
        / "restore-jobs"
        / "fuse-readable"
        / "TAPE001L5"
        / "games"
        / "foo.zip"
    )
    cached.parent.mkdir(parents=True)
    cached.write_bytes(b"x" * 1234)
    config["cache"] = {"path": str(tmp_path / "cache")}
    fs = fuse_fs.TapelibFuse(config)

    assert fs.read("/readable/TAPE001L5/games/foo.zip", 4, 10, None) == b"xxxx"
    assert db.list_jobs(config) == []


def test_write_inbox_cached_persists_file_and_queues_ingest_job(tmp_path):
    config = _config(tmp_path)
    config["cache"] = {"path": str(tmp_path / "cache")}
    _seed_catalog(config)
    fs = fuse_fs.TapelibFuse(config)

    fs.mkdir("/write/inbox-cached/new", 0o770)
    fh = fs.create("/write/inbox-cached/new/game.zip", 0o660)
    assert fs.write("/write/inbox-cached/new/game.zip", b"payload", 0, fh) == 7
    fs.flush("/write/inbox-cached/new/game.zip", fh)
    fs.release("/write/inbox-cached/new/game.zip", fh)

    cached = (
        tmp_path / "cache" / "write-inbox" / "inbox-cached" / "ready" / "new" / "game.zip"
    )
    assert cached.read_bytes() == b"payload"
    assert "game.zip" in fs.readdir("/write/inbox-cached/new", None)

    jobs = db.list_jobs(config)
    assert len(jobs) == 1
    assert jobs[0]["type"] == "ingest_cached_files"
    assert jobs[0]["state"] == "queued"
    assert jobs[0]["source"]["relative_path"] == "new/game.zip"

    with closing(db.connect(config)) as connection:
        rows = connection.execute("SELECT * FROM cache_entries").fetchall()
    assert len(rows) == 1
    assert rows[0]["cache_path"] == str(cached)
    assert rows[0]["state"] == "staged"
