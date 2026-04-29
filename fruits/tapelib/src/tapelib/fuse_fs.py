from __future__ import annotations

import errno
import grp
import json
import os
import pwd
import stat
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from fuse import FUSE, FuseOSError, Operations

from . import db
from . import hardware
from . import job_status


@dataclass(frozen=True)
class VirtualFile:
    content: bytes
    mode: int = stat.S_IFREG | 0o444
    mtime: int | None = None


@dataclass(frozen=True)
class CatalogFile:
    tape: str
    path: str
    size: int
    mode: int = stat.S_IFREG | 0o444


class TapelibFuse(Operations):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        fuse_config = config.get("fuse", {})
        self.uid = _uid_for_user(fuse_config.get("user", "ash"))
        self.gid = _gid_for_group(fuse_config.get("group", "users"))
        self.started_at = int(time.time())

    def getattr(self, path: str, fh: int | None = None) -> dict[str, int]:
        del fh
        if self._is_dir(path):
            return self._attrs(stat.S_IFDIR | 0o555, size=0)

        file_node = self._file_node(path)
        if file_node is None:
            raise FuseOSError(errno.ENOENT)
        if isinstance(file_node, CatalogFile):
            return self._attrs(file_node.mode, size=file_node.size)
        return self._attrs(
            file_node.mode, size=len(file_node.content), mtime=file_node.mtime
        )

    def readdir(self, path: str, fh: int | None) -> list[str]:
        del fh
        if not self._is_dir(path):
            raise FuseOSError(errno.ENOTDIR)
        return [".", "..", *sorted(self._children(path))]

    def open(self, path: str, flags: int) -> int:
        access_mode = flags & os.O_ACCMODE
        if access_mode != os.O_RDONLY:
            raise FuseOSError(errno.EROFS)
        file_node = self._file_node(path)
        if file_node is None:
            raise FuseOSError(errno.ENOENT)
        if isinstance(file_node, CatalogFile):
            raise FuseOSError(errno.EACCES)
        return 0

    def read(self, path: str, size: int, offset: int, fh: int | None) -> bytes:
        del fh
        file_node = self._file_node(path)
        if file_node is None:
            raise FuseOSError(errno.ENOENT)
        if isinstance(file_node, CatalogFile):
            raise FuseOSError(errno.EACCES)
        return file_node.content[offset : offset + size]

    def access(self, path: str, mode: int) -> int:
        if mode & os.W_OK:
            raise FuseOSError(errno.EROFS)
        if self._is_dir(path) or self._file_node(path) is not None:
            return 0
        raise FuseOSError(errno.ENOENT)

    def mkdir(self, path: str, mode: int) -> int:
        del path, mode
        raise FuseOSError(errno.EROFS)

    def mknod(self, path: str, mode: int, dev: int) -> int:
        del path, mode, dev
        raise FuseOSError(errno.EROFS)

    def create(self, path: str, mode: int, fi: Any = None) -> int:
        del path, mode, fi
        raise FuseOSError(errno.EROFS)

    def write(self, path: str, data: bytes, offset: int, fh: int | None) -> int:
        del path, data, offset, fh
        raise FuseOSError(errno.EROFS)

    def truncate(self, path: str, length: int, fh: int | None = None) -> int:
        del path, length, fh
        raise FuseOSError(errno.EROFS)

    def unlink(self, path: str) -> int:
        del path
        raise FuseOSError(errno.EROFS)

    def rmdir(self, path: str) -> int:
        del path
        raise FuseOSError(errno.EROFS)

    def rename(self, old: str, new: str) -> int:
        del old, new
        raise FuseOSError(errno.EROFS)

    def _attrs(
        self, mode: int, *, size: int, mtime: int | None = None
    ) -> dict[str, int]:
        timestamp = self.started_at if mtime is None else mtime
        return {
            "st_atime": timestamp,
            "st_ctime": timestamp,
            "st_gid": self.gid,
            "st_mode": mode,
            "st_mtime": timestamp,
            "st_nlink": 2 if stat.S_ISDIR(mode) else 1,
            "st_size": size,
            "st_uid": self.uid,
        }

    def _is_dir(self, path: str) -> bool:
        if path == "/":
            return True
        return path in self._dir_paths()

    def _children(self, path: str) -> Iterable[str]:
        if path == "/":
            return [
                "README.txt",
                "browse",
                "jobs",
                "readable",
                "system",
                "thumbnails",
                "write",
            ]
        return self._tree().get(path, set())

    def _file_node(self, path: str) -> VirtualFile | CatalogFile | None:
        if path == "/system/inventory.json":
            return _json_file(_inventory_payload(self.config))
        return self._files().get(path)

    def _dir_paths(self) -> set[str]:
        return set(self._tree().keys())

    def _tree(self) -> dict[str, set[str]]:
        tree: dict[str, set[str]] = {
            "/browse": set(),
            "/jobs": {
                "active",
                "complete",
                "failed",
                "jobs.json",
                "journal.json",
                "queued",
                "waiting",
            },
            "/jobs/active": {"jobs.json"},
            "/jobs/complete": {"jobs.json"},
            "/jobs/failed": {"jobs.json"},
            "/jobs/queued": {"jobs.json"},
            "/jobs/waiting": {"jobs.json"},
            "/readable": set(),
            "/system": {"config.json", "drives", "inventory.json", "status.json"},
            "/system/drives": set(),
            "/thumbnails": {"by-filetype", "cached", "README.txt"},
            "/thumbnails/by-filetype": {
                "folder.png",
                "iso.png",
                "unknown.png",
                "zip.png",
            },
            "/thumbnails/cached": {"README.txt"},
            "/write": {"inbox-cached", "inbox-direct", "README.txt"},
            "/write/inbox-cached": {"README.txt"},
            "/write/inbox-direct": {"README.txt"},
        }

        for tape in self._tape_names():
            _add_dir(tree, f"/browse/{tape}")
            _add_dir(tree, f"/readable/{tape}")
            tree[f"/browse/{tape}"].add("README.txt")
            tree[f"/readable/{tape}"].add("README.txt")

        for file_row in db.list_files(self.config):
            tape = file_row["tape_barcode"]
            browse_path = f"/browse/{tape}/{_clean_catalog_path(file_row['path'])}"
            readable_path = f"/readable/{tape}/{_clean_catalog_path(file_row['path'])}"
            _add_parent_dirs(tree, browse_path)
            _add_parent_dirs(tree, readable_path)

        for drive in db.list_drives(self.config):
            tree["/system/drives"].add(f"{drive['id']}.json")

        for job in db.list_jobs(self.config, limit=200):
            bucket = job_status.bucket_for_state(job["state"])
            if bucket is not None:
                tree[f"/jobs/{bucket}"].add(f"{job['id']}.json")

        return tree

    def _files(self) -> dict[str, VirtualFile | CatalogFile]:
        files: dict[str, VirtualFile | CatalogFile] = {
            "/README.txt": _json_file(
                {
                    "message": "tapelib is a catalog-first tape-library overlay.",
                    "browse": "Browse cached metadata. Reading browse files is disabled.",
                    "readable": "Readable paths will become queued retrieve jobs in a later milestone.",
                    "thumbnails": "Local thumbnail and filetype-icon sources live here.",
                    "write": "Cache-backed and direct write inboxes are not enabled in this FUSE mount yet.",
                }
            ),
            "/jobs/jobs.json": _json_file(
                {"jobs": db.list_jobs(self.config, limit=200)}
            ),
            "/jobs/journal.json": _json_file(
                {"events": db.list_job_events(self.config, limit=200)}
            ),
            "/thumbnails/README.txt": _text_file(
                "Thumbnail directories are local-only and must not force tape loads.\n"
            ),
            "/thumbnails/cached/README.txt": _text_file(
                "Cached thumbnails will be populated during indexing or ingest in a later milestone.\n"
            ),
            "/write/README.txt": _text_file(
                "Write inboxes are intentionally disabled in this first FUSE milestone.\n"
            ),
            "/write/inbox-cached/README.txt": _text_file(
                "Future writes here will land in the local tapelib cache before tape flush.\n"
            ),
            "/write/inbox-direct/README.txt": _text_file(
                "Future writes here will require preflight, checksum, target, and capacity checks.\n"
            ),
            "/system/config.json": _json_file(_public_config(self.config)),
            "/system/status.json": _json_file(_status_payload(self.config)),
        }

        for filetype in ["folder", "iso", "unknown", "zip"]:
            files[f"/thumbnails/by-filetype/{filetype}.png"] = _png_file()

        for state in ["active", "complete", "failed", "queued", "waiting"]:
            jobs = _jobs_for_bucket(self.config, state)
            files[f"/jobs/{state}/jobs.json"] = _json_file({"jobs": jobs})
            for job in jobs:
                files[f"/jobs/{state}/{job['id']}.json"] = _json_file(
                    job_status.snapshot(self.config, job["id"])
                )

        for drive in db.list_drives(self.config):
            files[f"/system/drives/{drive['id']}.json"] = _json_file(drive)

        for tape in self._tape_names():
            files[f"/browse/{tape}/README.txt"] = _text_file(
                "This directory is metadata-only. Opening archived file contents here is disabled.\n"
            )
            files[f"/readable/{tape}/README.txt"] = _text_file(
                "Readable retrieve paths are planned, but this mount does not load tapes yet.\n"
            )

        for file_row in db.list_files(self.config):
            tape = file_row["tape_barcode"]
            clean_path = _clean_catalog_path(file_row["path"])
            size = int(file_row["size_bytes"] or 0)
            files[f"/browse/{tape}/{clean_path}"] = CatalogFile(
                tape=tape, path=clean_path, size=size
            )
            files[f"/readable/{tape}/{clean_path}"] = _json_file(
                {
                    "error": "readable_retrieve_not_implemented",
                    "message": "Opening this readable file will become a queued retrieve job in a later milestone.",
                    "tape": tape,
                    "path": clean_path,
                    "size_bytes": size,
                }
            )

        return files

    def _tape_names(self) -> list[str]:
        db_tapes = [row["barcode"] for row in db.list_tapes(self.config)]
        configured_tapes = self.config.get("games", {}).get("selectedTapes", [])
        return sorted(set(db_tapes + configured_tapes))


def mount(
    config: dict[str, Any], mount_point: str, *, foreground: bool, allow_other: bool
) -> None:
    db.initialize_database(config)
    os.makedirs(mount_point, exist_ok=True)
    options = {
        "foreground": foreground,
        "ro": True,
        "nothreads": True,
    }
    if allow_other:
        options["allow_other"] = True
        options["default_permissions"] = True
    FUSE(TapelibFuse(config), mount_point, **options)


def _add_dir(tree: dict[str, set[str]], path: str) -> None:
    parent, name = _split_parent(path)
    tree.setdefault(path, set())
    tree.setdefault(parent, set()).add(name)


def _add_parent_dirs(tree: dict[str, set[str]], file_path: str) -> None:
    parent = str(PurePosixPath(file_path).parent)
    current = ""
    for part in PurePosixPath(parent).parts:
        if part == "/":
            current = ""
            continue
        current = f"{current}/{part}"
        _add_dir(tree, current)
    tree.setdefault(parent, set()).add(PurePosixPath(file_path).name)


def _split_parent(path: str) -> tuple[str, str]:
    pure = PurePosixPath(path)
    parent = str(pure.parent)
    if parent == ".":
        parent = "/"
    return parent, pure.name


def _clean_catalog_path(path: str) -> str:
    return str(PurePosixPath("/") / path.lstrip("/")).lstrip("/")


def _json_file(payload: Any) -> VirtualFile:
    return VirtualFile(
        (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def _text_file(text: str) -> VirtualFile:
    return VirtualFile(text.encode("utf-8"))


def _png_file() -> VirtualFile:
    # 1x1 transparent PNG placeholder for file-browser thumbnail isolation.
    return VirtualFile(
        bytes.fromhex(
            "89504e470d0a1a0a"
            "0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6360000002000100ffff03000006000557bfab82"
            "0000000049454e44ae426082"
        )
    )


def _uid_for_user(user: str) -> int:
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError:
        return os.getuid()


def _gid_for_group(group: str) -> int:
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
        return os.getgid()


def _inventory_payload(config: dict[str, Any]) -> dict[str, Any]:
    library = config.get("library", {})
    drives = library.get("drives", [])
    changer = hardware.read_changer_inventory(library.get("changerDevice")).as_dict()
    return {
        "changer": changer,
        "changer_device": library.get("changerDevice"),
        "drive_count": len(drives),
        "drives": drives,
        "selected_tapes": config.get("games", {}).get("selectedTapes", []),
    }


def _status_payload(config: dict[str, Any]) -> dict[str, Any]:
    status_path = os.path.join(
        config.get("stateDir", "/var/lib/tapelib"), "status", "status.json"
    )
    runtime_status: dict[str, Any] = {}
    if os.path.exists(status_path):
        with open(status_path, encoding="utf-8") as handle:
            runtime_status = json.load(handle)
    return {
        "database": db.initialize_database(config),
        "runtime": runtime_status,
    }


def _public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "cache": config.get("cache", {}),
        "database": config.get("database", {}),
        "fuse": config.get("fuse", {}),
        "games": config.get("games", {}),
        "library": config.get("library", {}),
        "stateDir": config.get("stateDir"),
        "webui": config.get("webui", {}),
    }


def _jobs_for_bucket(config: dict[str, Any], bucket: str) -> list[dict[str, Any]]:
    if bucket == "queued":
        states = ["created", "queued"]
    elif bucket == "waiting":
        states = [
            "waiting_for_cache",
            "waiting_for_changer",
            "waiting_for_mount",
            "needs_operator",
        ]
    elif bucket == "active":
        states = [
            "loading_tape",
            "mounting_ltfs",
            "running",
            "verifying",
            "updating_catalog",
            "unmounting",
            "unloading",
        ]
    elif bucket == "failed":
        states = ["failed"]
    elif bucket == "complete":
        states = ["complete"]
    else:
        states = []

    jobs = []
    for state in states:
        jobs.extend(db.list_jobs(config, state=state, limit=200))
    return jobs
