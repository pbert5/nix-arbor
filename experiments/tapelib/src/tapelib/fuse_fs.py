from __future__ import annotations

import errno
import grp
import json
import os
import pwd
import stat
import time
import uuid
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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


@dataclass(frozen=True)
class ReadableFile:
    tape: str
    path: str
    size: int
    checksum_sha256: str | None = None
    bundle_path: str | None = None
    mode: int = stat.S_IFREG | 0o444


@dataclass(frozen=True)
class LocalCachedFile:
    path: Path
    size: int
    mode: int = stat.S_IFREG | 0o660


ROOT_CHILDREN = {
    "README.txt",
    "browse",
    "jobs",
    "readable",
    "system",
    "thumbnails",
    "write",
}

STATIC_TREE = {
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

JOB_BUCKET_PATHS = {
    "/jobs/active": "active",
    "/jobs/complete": "complete",
    "/jobs/failed": "failed",
    "/jobs/queued": "queued",
    "/jobs/waiting": "waiting",
}

INVENTORY_PLACEHOLDER_SIZE = 64 * 1024


class TapelibFuse(Operations):
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        db.initialize_database(config)
        self.connection = db.connect(config)
        fuse_config = config.get("fuse", {})
        self.uid = _uid_for_user(fuse_config.get("user", "ash"))
        self.gid = _gid_for_group(fuse_config.get("group", "users"))
        self.metadata_cache_seconds = float(
            fuse_config.get("metadataCacheSeconds", 1.0)
        )
        self.started_at = int(time.time())
        self._next_fh = 1
        self._open_writes: dict[int, dict[str, Any]] = {}
        self._tree_cache: tuple[float, dict[str, set[str]]] | None = None
        self._files_cache: tuple[
            float, dict[str, VirtualFile | CatalogFile | ReadableFile]
        ] | None = None

    def getattr(self, path: str, fh: int | None = None) -> dict[str, int]:
        del fh
        if path == "/system/inventory.json":
            return self._attrs(
                stat.S_IFREG | 0o444, size=INVENTORY_PLACEHOLDER_SIZE
            )
        fast_node = self._fast_file_node(path)
        if fast_node is not None:
            return self._attrs(
                fast_node.mode,
                size=len(fast_node.content),
                mtime=fast_node.mtime,
            )
        if self._is_dir(path):
            mode = stat.S_IFDIR | (0o770 if _is_write_inbox_path(path) else 0o555)
            return self._attrs(mode, size=0)

        file_node = self._file_node(path)
        if file_node is None:
            raise FuseOSError(errno.ENOENT)
        if isinstance(file_node, (CatalogFile, ReadableFile, LocalCachedFile)):
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
        if isinstance(file_node, LocalCachedFile):
            return 0
        if isinstance(file_node, CatalogFile):
            raise FuseOSError(errno.EACCES)
        if isinstance(file_node, ReadableFile):
            self._queue_readable_file(file_node)
        return 0

    def read(self, path: str, size: int, offset: int, fh: int | None) -> bytes:
        del fh
        file_node = self._file_node(path)
        if file_node is None:
            raise FuseOSError(errno.ENOENT)
        if isinstance(file_node, CatalogFile):
            raise FuseOSError(errno.EACCES)
        if isinstance(file_node, LocalCachedFile):
            with file_node.path.open("rb") as handle:
                handle.seek(offset)
                return handle.read(size)
        if isinstance(file_node, ReadableFile):
            return self._read_readable_file(file_node, size, offset)
        return file_node.content[offset : offset + size]

    def access(self, path: str, mode: int) -> int:
        if mode & os.W_OK:
            if _is_write_inbox_path(path):
                return 0
            raise FuseOSError(errno.EROFS)
        if self._is_dir(path) or self._file_node(path) is not None:
            return 0
        raise FuseOSError(errno.ENOENT)

    def mkdir(self, path: str, mode: int) -> int:
        del mode
        if not _is_write_inbox_path(path):
            raise FuseOSError(errno.EROFS)
        relative = _write_inbox_relative(path)
        if relative is None:
            raise FuseOSError(errno.EEXIST)
        _write_inbox_ready_path(self.config, relative).mkdir(parents=True, exist_ok=True)
        return 0

    def mknod(self, path: str, mode: int, dev: int) -> int:
        del path, mode, dev
        raise FuseOSError(errno.EROFS)

    def create(self, path: str, mode: int, fi: Any = None) -> int:
        del mode, fi
        if not _is_write_inbox_path(path):
            raise FuseOSError(errno.EROFS)
        relative = _write_inbox_relative(path)
        if relative is None:
            raise FuseOSError(errno.EISDIR)
        final_path = _write_inbox_ready_path(self.config, relative)
        if final_path.exists():
            raise FuseOSError(errno.EEXIST)
        partial_root = _write_inbox_partial_root(self.config)
        partial_root.mkdir(parents=True, exist_ok=True)
        partial_path = partial_root / f"{uuid.uuid4().hex}.partial"
        handle = partial_path.open("w+b")
        fh = self._next_fh
        self._next_fh += 1
        self._open_writes[fh] = {
            "handle": handle,
            "partial_path": partial_path,
            "final_path": final_path,
            "relative_path": relative,
            "fuse_path": path,
        }
        return fh

    def write(self, path: str, data: bytes, offset: int, fh: int | None) -> int:
        del path
        if fh not in self._open_writes:
            raise FuseOSError(errno.EBADF)
        handle = self._open_writes[fh]["handle"]
        handle.seek(offset)
        handle.write(data)
        return len(data)

    def flush(self, path: str, fh: int | None) -> int:
        del path
        if fh not in self._open_writes:
            return 0
        handle = self._open_writes[fh]["handle"]
        handle.flush()
        os.fsync(handle.fileno())
        return 0

    def release(self, path: str, fh: int | None) -> int:
        del path
        if fh not in self._open_writes:
            return 0
        write_state = self._open_writes.pop(fh)
        handle = write_state["handle"]
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        final_path = write_state["final_path"]
        final_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(write_state["partial_path"], final_path)
        _queue_cached_ingest(
            self.config,
            relative_path=write_state["relative_path"],
            cache_path=final_path,
            fuse_path=write_state["fuse_path"],
        )
        return 0

    def truncate(self, path: str, length: int, fh: int | None = None) -> int:
        del path, length, fh
        raise FuseOSError(errno.EROFS)

    def unlink(self, path: str) -> int:
        if _is_write_inbox_path(path):
            relative = _write_inbox_relative(path)
            if relative is None:
                raise FuseOSError(errno.EISDIR)
            try:
                _write_inbox_ready_path(self.config, relative).unlink()
            except FileNotFoundError:
                raise FuseOSError(errno.ENOENT) from None
            return 0
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
        if _is_write_inbox_path(path):
            relative = _write_inbox_relative(path)
            if relative is None:
                return True
            return _write_inbox_ready_path(self.config, relative).is_dir()
        if path in STATIC_TREE:
            return True
        shallow_tape_dir = self._shallow_tape_dir(path)
        if shallow_tape_dir is not None:
            return shallow_tape_dir in self._tape_names()
        catalog_path = self._catalog_mount_path(path)
        if catalog_path is not None:
            _prefix, tape, archive_path = catalog_path
            return db.catalog_path_has_children_with_connection(
                self.connection, tape_barcode=tape, parent_path=archive_path
            )
        return path in self._dir_paths()

    def _children(self, path: str) -> Iterable[str]:
        if path == "/":
            return ROOT_CHILDREN
        if _is_write_inbox_path(path):
            static_children = set(STATIC_TREE.get(path, set()))
            relative = _write_inbox_relative(path)
            backing = (
                _write_inbox_ready_root(self.config)
                if relative is None
                else _write_inbox_ready_path(self.config, relative)
            )
            if backing.is_dir():
                static_children.update(child.name for child in backing.iterdir())
            return static_children
        if path == "/browse" or path == "/readable":
            return self._tape_names()
        if self._shallow_tape_dir(path) is not None:
            return {"README.txt"}
        if path == "/system/drives":
            return {
                f"{drive['id']}.json"
                for drive in db.list_drives_with_connection(self.connection)
            }
        if path in JOB_BUCKET_PATHS:
            return set(STATIC_TREE[path]) | {
                f"{job['id']}.json"
                for job in _jobs_for_bucket(self.connection, JOB_BUCKET_PATHS[path])
            }
        if path in STATIC_TREE:
            return STATIC_TREE[path]
        catalog_path = self._catalog_mount_path(path)
        if catalog_path is not None:
            _prefix, tape, archive_path = catalog_path
            return db.list_catalog_child_names_with_connection(
                self.connection, tape_barcode=tape, parent_path=archive_path
            )
        return self._tree().get(path, set())

    def _file_node(
        self, path: str
    ) -> VirtualFile | CatalogFile | ReadableFile | LocalCachedFile | None:
        if path == "/system/inventory.json":
            return _json_file(_inventory_payload(self.config))
        if _is_write_inbox_path(path):
            relative = _write_inbox_relative(path)
            if relative is not None:
                backing = _write_inbox_ready_path(self.config, relative)
                if backing.is_file():
                    return LocalCachedFile(path=backing, size=backing.stat().st_size)
        fast_node = self._fast_file_node(path)
        if fast_node is not None:
            return fast_node
        catalog_node = self._catalog_file_node(path)
        if catalog_node is not None:
            return catalog_node
        if self._catalog_mount_path(path) is not None:
            return None
        return self._files().get(path)

    def _dir_paths(self) -> set[str]:
        return set(self._tree().keys())

    def _tree(self) -> dict[str, set[str]]:
        now = time.monotonic()
        if self._tree_cache is not None:
            cached_at, cached_tree = self._tree_cache
            if self._cache_is_fresh(cached_at, now):
                return cached_tree

        tree = self._build_tree()
        self._tree_cache = (now, tree)
        return tree

    def _build_tree(self) -> dict[str, set[str]]:
        tree: dict[str, set[str]] = {
            path: set(children) for path, children in STATIC_TREE.items()
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

        for bundle_row in db.list_bundle_members(self.config):
            tape = bundle_row["tape_barcode"]
            browse_path = f"/browse/{tape}/{_clean_catalog_path(bundle_row['member_path'])}"
            readable_path = f"/readable/{tape}/{_clean_catalog_path(bundle_row['member_path'])}"
            _add_parent_dirs(tree, browse_path)
            _add_parent_dirs(tree, readable_path)

        for drive in db.list_drives_with_connection(self.connection):
            tree["/system/drives"].add(f"{drive['id']}.json")

        for job in db.list_jobs_with_connection(self.connection, limit=200):
            bucket = job_status.bucket_for_state(job["state"])
            if bucket is not None:
                tree[f"/jobs/{bucket}"].add(f"{job['id']}.json")

        return tree

    def _files(self) -> dict[str, VirtualFile | CatalogFile | ReadableFile]:
        now = time.monotonic()
        if self._files_cache is not None:
            cached_at, cached_files = self._files_cache
            if self._cache_is_fresh(cached_at, now):
                return cached_files

        files = self._build_files()
        self._files_cache = (now, files)
        return files

    def _build_files(self) -> dict[str, VirtualFile | CatalogFile | ReadableFile]:
        files: dict[str, VirtualFile | CatalogFile | ReadableFile] = {
            "/README.txt": _json_file(
                {
                    "message": "tapelib is a catalog-first tape-library overlay.",
                    "browse": "Browse cached metadata. Reading browse files is disabled.",
                    "readable": "Opening readable paths queues retrieve jobs into the local restore cache.",
                    "thumbnails": "Local thumbnail and filetype-icon sources live here.",
                    "write": "Cache-backed and direct write inboxes are not enabled in this FUSE mount yet.",
                }
            ),
            "/jobs/jobs.json": _json_file(
                {
                    "jobs": [
                        _compact_job(job)
                        for job in db.list_jobs_with_connection(
                            self.connection, limit=200
                        )
                    ]
                }
            ),
            "/jobs/journal.json": _json_file(
                {"events": db.list_job_events_with_connection(self.connection, limit=200)}
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
            "/system/status.json": _json_file(
                _status_payload(self.config, self.connection)
            ),
        }

        for filetype in ["folder", "iso", "unknown", "zip"]:
            files[f"/thumbnails/by-filetype/{filetype}.png"] = _png_file()

        for state in ["active", "complete", "failed", "queued", "waiting"]:
            jobs = _jobs_for_bucket(self.connection, state)
            files[f"/jobs/{state}/jobs.json"] = _json_file(
                {"jobs": [_compact_job(job) for job in jobs]}
            )
            for job in jobs:
                files[f"/jobs/{state}/{job['id']}.json"] = _json_file(
                    job_status.snapshot(self.config, job["id"])
                )

        for drive in db.list_drives_with_connection(self.connection):
            files[f"/system/drives/{drive['id']}.json"] = _json_file(drive)

        for tape in self._tape_names():
            files[f"/browse/{tape}/README.txt"] = _text_file(
                "This directory is metadata-only. Opening archived file contents here is disabled.\n"
            )
            files[f"/readable/{tape}/README.txt"] = _text_file(
                "Opening files here queues a restore into the local tapelib cache and returns JSON status until cached content is ready.\n"
            )

        for file_row in db.list_files(self.config):
            tape = file_row["tape_barcode"]
            clean_path = _clean_catalog_path(file_row["path"])
            size = int(file_row["size_bytes"] or 0)
            files[f"/browse/{tape}/{clean_path}"] = CatalogFile(
                tape=tape, path=clean_path, size=size
            )
            files[f"/readable/{tape}/{clean_path}"] = ReadableFile(
                tape=tape,
                path=clean_path,
                size=size,
                checksum_sha256=file_row.get("checksum_sha256"),
            )

        for bundle_row in db.list_bundle_members(self.config):
            tape = bundle_row["tape_barcode"]
            clean_path = _clean_catalog_path(bundle_row["member_path"])
            size = int(bundle_row["size_bytes"] or 0)
            files[f"/browse/{tape}/{clean_path}"] = CatalogFile(
                tape=tape, path=clean_path, size=size
            )
            files[f"/readable/{tape}/{clean_path}"] = _json_file(
                _bundled_readable_payload(tape, clean_path, bundle_row, size)
            )

        return files

    def _cache_is_fresh(self, cached_at: float, now: float) -> bool:
        return (
            self.metadata_cache_seconds > 0
            and now - cached_at <= self.metadata_cache_seconds
        )

    def _shallow_tape_dir(self, path: str) -> str | None:
        parts = PurePosixPath(path).parts
        if (
            len(parts) == 3
            and parts[0] == "/"
            and parts[1] in {"browse", "readable"}
        ):
            return parts[2]
        return None

    def _catalog_mount_path(self, path: str) -> tuple[str, str, str] | None:
        parts = PurePosixPath(path).parts
        if len(parts) < 4 or parts[0] != "/" or parts[1] not in {"browse", "readable"}:
            return None
        tape = parts[2]
        if tape not in self._tape_names():
            return None
        return parts[1], tape, str(PurePosixPath(*parts[3:]))

    def _catalog_file_node(
        self, path: str
    ) -> CatalogFile | ReadableFile | VirtualFile | None:
        catalog_path = self._catalog_mount_path(path)
        if catalog_path is None:
            return None
        prefix, tape, archive_path = catalog_path
        file_row = db.get_file_with_connection(
            self.connection, tape_barcode=tape, path=archive_path
        )
        if file_row is not None:
            clean_path = _clean_catalog_path(file_row["path"])
            size = int(file_row["size_bytes"] or 0)
            if prefix == "browse":
                return CatalogFile(tape=tape, path=clean_path, size=size)
            return ReadableFile(
                tape=tape,
                path=clean_path,
                size=size,
                checksum_sha256=file_row.get("checksum_sha256"),
            )

        bundle_row = db.get_bundle_member_with_connection(
            self.connection, tape_barcode=tape, member_path=archive_path
        )
        if bundle_row is None:
            return None
        clean_path = _clean_catalog_path(bundle_row["member_path"])
        size = int(bundle_row["size_bytes"] or 0)
        if prefix == "browse":
            return CatalogFile(tape=tape, path=clean_path, size=size)
        return _json_file(_bundled_readable_payload(tape, clean_path, bundle_row, size))

    def _fast_file_node(self, path: str) -> VirtualFile | None:
        if path == "/README.txt":
            return _json_file(
                {
                    "message": "tapelib is a catalog-first tape-library overlay.",
                    "browse": "Browse cached metadata. Reading browse files is disabled.",
                    "readable": "Opening readable paths queues retrieve jobs into the local restore cache.",
                    "thumbnails": "Local thumbnail and filetype-icon sources live here.",
                    "write": "Cache-backed and direct write inboxes are not enabled in this FUSE mount yet.",
                }
            )
        if path == "/jobs/jobs.json":
            return _json_file(
                {
                    "jobs": [
                        _compact_job(job)
                        for job in db.list_jobs_with_connection(
                            self.connection, limit=200
                        )
                    ]
                }
            )
        if path == "/jobs/journal.json":
            return _json_file(
                {"events": db.list_job_events_with_connection(self.connection, limit=200)}
            )
        if path == "/system/config.json":
            return _json_file(_public_config(self.config))
        if path == "/system/status.json":
            return _json_file(_status_payload(self.config, self.connection))
        if path == "/thumbnails/README.txt":
            return _text_file(
                "Thumbnail directories are local-only and must not force tape loads.\n"
            )
        if path == "/thumbnails/cached/README.txt":
            return _text_file(
                "Cached thumbnails will be populated during indexing or ingest in a later milestone.\n"
            )
        if path in {
            "/thumbnails/by-filetype/folder.png",
            "/thumbnails/by-filetype/iso.png",
            "/thumbnails/by-filetype/unknown.png",
            "/thumbnails/by-filetype/zip.png",
        }:
            return _png_file()
        if path == "/write/README.txt":
            return _text_file(
                "Write inboxes are intentionally disabled in this first FUSE milestone.\n"
            )
        if path == "/write/inbox-cached/README.txt":
            return _text_file(
                "Future writes here will land in the local tapelib cache before tape flush.\n"
            )
        if path == "/write/inbox-direct/README.txt":
            return _text_file(
                "Future writes here will require preflight, checksum, target, and capacity checks.\n"
            )

        for prefix in ("/browse/", "/readable/"):
            if not path.startswith(prefix) or not path.endswith("/README.txt"):
                continue
            tape_path = path.removeprefix(prefix).removesuffix("/README.txt")
            if "/" in tape_path or tape_path not in self._tape_names():
                continue
            if prefix == "/browse/":
                return _text_file(
                    "This directory is metadata-only. Opening archived file contents here is disabled.\n"
                )
            return _text_file(
                "Opening files here queues a restore into the local tapelib cache and returns JSON status until cached content is ready.\n"
            )

        drive_prefix = "/system/drives/"
        if path.startswith(drive_prefix) and path.endswith(".json"):
            drive_id = path.removeprefix(drive_prefix).removesuffix(".json")
            for drive in db.list_drives_with_connection(self.connection):
                if drive["id"] == drive_id:
                    return _json_file(drive)
            return None

        for bucket_path, bucket in JOB_BUCKET_PATHS.items():
            if path == f"{bucket_path}/jobs.json":
                return _json_file(
                    {
                        "jobs": [
                            _compact_job(job)
                            for job in _jobs_for_bucket(self.connection, bucket)
                        ]
                    }
                )
            if path.startswith(f"{bucket_path}/") and path.endswith(".json"):
                job_id = path.removeprefix(f"{bucket_path}/").removesuffix(".json")
                try:
                    return _json_file(job_status.snapshot(self.config, job_id))
                except KeyError:
                    return None

        return None

    def _tape_names(self) -> list[str]:
        db_tapes = [
            row["barcode"] for row in db.list_tapes_with_connection(self.connection)
        ]
        configured_tapes = self.config.get("games", {}).get("selectedTapes", [])
        return sorted(set(db_tapes + configured_tapes))

    def _read_readable_file(
        self, file_node: ReadableFile, size: int, offset: int
    ) -> bytes:
        cached_path = _readable_destination_path(self.config, file_node)
        if _cached_readable_is_ready(cached_path, file_node):
            with cached_path.open("rb") as handle:
                handle.seek(offset)
                return handle.read(size)

        payload = self._queue_readable_file(file_node)
        content = (
            json.dumps(payload, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        return content[offset : offset + size]

    def _queue_readable_file(self, file_node: ReadableFile) -> dict[str, Any]:
        if file_node.bundle_path is not None:
            return _bundled_readable_payload(
                file_node.tape,
                file_node.path,
                {
                    "bundle_path": file_node.bundle_path,
                    "checksum_sha256": file_node.checksum_sha256,
                },
                file_node.size,
            )

        destination_root = _readable_restore_root(self.config)
        destination_path = _readable_destination_path(self.config, file_node)
        requested_file = {
            "tape_barcode": file_node.tape,
            "archive_path": file_node.path,
            "destination_path": str(destination_path),
            "size_bytes": file_node.size,
            "checksum_sha256": file_node.checksum_sha256,
        }
        source = {
            "kind": "fuse_readable",
            "layout": "preserve_tape_and_archive_path",
            "files": [requested_file],
        }
        target = {
            "destination_root": str(destination_root),
            "groups": [
                {
                    "tape_barcode": file_node.tape,
                    "file_count": 1,
                    "total_bytes": file_node.size,
                    "files": [requested_file],
                }
            ],
        }
        queue_states = [
            "created",
            "queued",
            "waiting_for_cache",
            "waiting_for_drive",
            "waiting_for_changer",
            "waiting_for_mount",
        ]

        db.initialize_database(self.config)
        with closing(db.connect(self.config)) as connection:
            with connection:
                existing = db.find_matching_job(
                    connection,
                    "retrieve_files",
                    states=queue_states,
                    source=source,
                    target=target,
                )
                if existing is not None:
                    db.append_job_event(
                        connection,
                        existing["id"],
                        "readable_retrieve_joined",
                        "Readable FUSE access joined an existing retrieve job.",
                        {
                            "tape_barcode": file_node.tape,
                            "archive_path": file_node.path,
                            "destination_path": str(destination_path),
                        },
                    )
                    job = db.get_job(connection, existing["id"])
                    coalesced = True
                else:
                    job = db.create_job_with_connection(
                        connection,
                        "retrieve_files",
                        state="queued",
                        source=source,
                        target=target,
                        required_bytes=file_node.size,
                    )
                    db.append_job_event(
                        connection,
                        job["id"],
                        "readable_retrieve_queued",
                        "Readable FUSE access queued a retrieve job.",
                        {
                            "tape_barcode": file_node.tape,
                            "archive_path": file_node.path,
                            "destination_path": str(destination_path),
                        },
                    )
                    job = db.get_job(connection, job["id"])
                    coalesced = False

        return {
            "cache_status": "queued",
            "coalesced": coalesced,
            "destination_path": str(destination_path),
            "job_id": job["id"],
            "message": "Retrieve queued. Check /mnt/tapelib/jobs for progress.",
            "path": file_node.path,
            "state": job["state"],
            "tape": file_node.tape,
        }


def mount(
    config: dict[str, Any], mount_point: str, *, foreground: bool, allow_other: bool
) -> None:
    db.initialize_database(config)
    os.makedirs(mount_point, exist_ok=True)
    options = {
        "foreground": foreground,
        "ro": False,
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


def _compact_job(job: dict[str, Any]) -> dict[str, Any]:
    compact = dict(job)
    source = compact.get("source")
    if isinstance(source, dict) and isinstance(source.get("files"), list):
        source = dict(source)
        source["file_count"] = len(source.pop("files"))
        compact["source"] = source
    target = compact.get("target")
    if isinstance(target, dict) and isinstance(target.get("groups"), list):
        target = dict(target)
        target["group_count"] = len(target["groups"])
        target.pop("groups")
        compact["target"] = target
    return compact


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


def _status_payload(
    config: dict[str, Any], connection: Any | None = None
) -> dict[str, Any]:
    status_path = os.path.join(
        config.get("stateDir", "/var/lib/tapelib"), "status", "status.json"
    )
    runtime_status: dict[str, Any] = {}
    if os.path.exists(status_path):
        with open(status_path, encoding="utf-8") as handle:
            runtime_status = json.load(handle)
    return {
        "database": (
            db.database_summary(connection)
            if connection is not None
            else db.initialize_database(config)
        ),
        "runtime": runtime_status,
    }


def _public_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "cache": config.get("cache", {}),
        "database": config.get("database", {}),
        "fuse": config.get("fuse", {}),
        "games": config.get("games", {}),
        "library": config.get("library", {}),
        "scheduler": config.get("scheduler", {}),
        "stateDir": config.get("stateDir"),
        "webui": config.get("webui", {}),
    }


def _readable_restore_root(config: dict[str, Any]) -> Path:
    return Path(config.get("cache", {}).get("path", "/run/media/ash/cache/tapelib")) / "restore-jobs" / "fuse-readable"


def _readable_destination_path(config: dict[str, Any], file_node: ReadableFile) -> Path:
    return _readable_restore_root(config) / file_node.tape / file_node.path


def _cached_readable_is_ready(path: Path, file_node: ReadableFile) -> bool:
    try:
        return path.is_file() and path.stat().st_size == file_node.size
    except OSError:
        return False


def _is_write_inbox_path(path: str) -> bool:
    return path == "/write/inbox-cached" or path.startswith("/write/inbox-cached/")


def _write_inbox_relative(path: str) -> str | None:
    pure = PurePosixPath(path)
    parts = pure.parts
    if len(parts) < 3 or parts[:3] != ("/", "write", "inbox-cached"):
        return None
    relative_parts = parts[3:]
    if relative_parts == ():
        return None
    if any(part in {"", ".", ".."} for part in relative_parts):
        raise FuseOSError(errno.EINVAL)
    return str(PurePosixPath(*relative_parts))


def _write_inbox_root(config: dict[str, Any]) -> Path:
    return Path(config.get("cache", {}).get("path", "/run/media/ash/cache/tapelib")) / "write-inbox" / "inbox-cached"


def _write_inbox_ready_root(config: dict[str, Any]) -> Path:
    return _write_inbox_root(config) / "ready"


def _write_inbox_partial_root(config: dict[str, Any]) -> Path:
    return _write_inbox_root(config) / "partial"


def _write_inbox_ready_path(config: dict[str, Any], relative_path: str) -> Path:
    return _write_inbox_ready_root(config) / relative_path


def _queue_cached_ingest(
    config: dict[str, Any],
    *,
    relative_path: str,
    cache_path: Path,
    fuse_path: str,
) -> dict[str, Any]:
    size_bytes = cache_path.stat().st_size
    namespace = config.get("games", {}).get("namespacePrefix", "/ingest")
    source = {
        "kind": "fuse_inbox_cached",
        "fuse_path": fuse_path,
        "relative_path": relative_path,
        "cache_path": str(cache_path),
    }
    target = {
        "namespace_prefix": namespace,
        "policy": "queue_only",
    }
    db.initialize_database(config)
    with closing(db.connect(config)) as connection:
        with connection:
            job = db.create_job_with_connection(
                connection,
                "ingest_cached_files",
                state="queued",
                source=source,
                target=target,
                required_bytes=size_bytes,
            )
            connection.execute(
                """
                INSERT INTO cache_entries (
                  job_id, source_path, cache_path, size_bytes,
                  checksum_sha256, state, created_at
                ) VALUES (?, ?, ?, ?, NULL, 'staged', ?)
                """,
                (
                    job["id"],
                    f"fuse://{fuse_path}",
                    str(cache_path),
                    size_bytes,
                    db.utc_now(),
                ),
            )
            db.append_job_event(
                connection,
                job["id"],
                "ingest_file_queued",
                "Cached FUSE inbox file queued for archive planning.",
                source | {"size_bytes": size_bytes},
            )
            return db.get_job(connection, job["id"])


def _bundled_readable_payload(
    tape: str,
    path: str,
    bundle_row: dict[str, Any],
    size: int,
) -> dict[str, Any]:
    return {
        "error": "bundled_retrieve_not_implemented",
        "message": "This catalog entry is previewed from a tar bundle on tape; direct queued extraction is not implemented yet.",
        "tape": tape,
        "path": path,
        "bundle_path": bundle_row["bundle_path"],
        "size_bytes": size,
    }


def _jobs_for_bucket(connection: Any, bucket: str) -> list[dict[str, Any]]:
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
        jobs.extend(db.list_jobs_with_connection(connection, state=state, limit=200))
    return jobs
