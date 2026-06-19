# Tapelib Filesystem Operation Matrix

This is the user-facing operation list for `/mnt/tapelib` and the usual
`/home/example/tapelib` symlink.

## Root

| Path | Operation | Expected Behavior | Tape Work |
|------|-----------|-------------------|-----------|
| `/` | `stat`, `readdir`, `access R_OK` | Lists the top-level virtual areas. | none |
| `/README.txt` | `stat`, `read` | Returns a short JSON orientation note. | none |
| `/` | create/write/rename/delete | Rejected read-only. | none |

## Browse

| Path | Operation | Expected Behavior | Tape Work |
|------|-----------|-------------------|-----------|
| `/browse` | `stat`, `readdir` | Lists known tape barcodes from catalog/config. | none |
| `/browse/<tape>` | `stat`, `readdir` | Lists a tape root and `README.txt`; deeper paths expose catalog metadata. | none |
| `/browse/<tape>/README.txt` | `read` | Explains that browse is metadata-only. | none |
| `/browse/<tape>/<archive-path>` | `stat` | Reports catalog size/mode for archived files. | none |
| `/browse/<tape>/<archive-path>` | `open`, `read` | Rejected with access denied; browse never queues restore. | none |

## Readable

| Path | Operation | Expected Behavior | Tape Work |
|------|-----------|-------------------|-----------|
| `/readable` | `stat`, `readdir` | Lists known tape barcodes. | none |
| `/readable/<tape>` | `stat`, `readdir` | Lists a tape root and `README.txt`; deeper paths expose readable catalog entries. | none |
| `/readable/<tape>/README.txt` | `read` | Explains queued restore behavior. | none |
| `/readable/<tape>/<archive-path>` | `stat` | Reports catalog size/mode. | none |
| `/readable/<tape>/<archive-path>` | `open`, `read` when cached | Streams the restored local cached file. | none |
| `/readable/<tape>/<archive-path>` | `open`, `read` when not cached | Queues or joins a retrieve job and returns JSON status. | queues work; tape moves only when a queue runner executes it |
| `/readable/<tape>/<bundled-member>` | `read` | Returns bundled-member metadata placeholder for now. | none |

## Jobs

| Path | Operation | Expected Behavior | Tape Work |
|------|-----------|-------------------|-----------|
| `/jobs` | `stat`, `readdir` | Lists status buckets and summary JSON files. | none |
| `/jobs/jobs.json` | `read` | Recent compact job summaries from SQLite. Large file/group lists are counted instead of embedded. | none |
| `/jobs/journal.json` | `read` | Recent job events from SQLite. | none |
| `/jobs/<bucket>` | `stat`, `readdir` | Lists `jobs.json` plus job snapshot files in that bucket. | none |
| `/jobs/<bucket>/jobs.json` | `read` | Per-bucket compact job summary. Large file/group lists are counted instead of embedded. | none |
| `/jobs/<bucket>/<job-id>.json` | `read` | Progress-oriented job snapshot. | none |

## System

| Path | Operation | Expected Behavior | Tape Work |
|------|-----------|-------------------|-----------|
| `/system` | `stat`, `readdir` | Lists config, status, inventory, and drives. | none |
| `/system/config.json` | `read` | Public tapelib config view. | none |
| `/system/status.json` | `read` | Runtime/database status. | none |
| `/system/drives` | `stat`, `readdir` | Lists configured drive JSON files. | none |
| `/system/drives/<drive>.json` | `read` | Drive state from SQLite/config. | none |
| `/system/inventory.json` | `stat` | Cheap bounded placeholder stat for file-manager probes. | none |
| `/system/inventory.json` | `read` | Live changer inventory using `mtx status`. | hardware observation, can be slow |

## Thumbnails

| Path | Operation | Expected Behavior | Tape Work |
|------|-----------|-------------------|-----------|
| `/thumbnails` | `stat`, `readdir` | Lists local placeholder thumbnail areas. | none |
| `/thumbnails/README.txt` | `read` | Explains thumbnail isolation. | none |
| `/thumbnails/by-filetype/*.png` | `stat`, `read` | Returns tiny local placeholder PNGs. | none |
| `/thumbnails/cached/README.txt` | `read` | Reserved cache note. | none |

## Write Inbox

| Path | Operation | Expected Behavior | Tape Work |
|------|-----------|-------------------|-----------|
| `/write` | `stat`, `readdir` | Lists write inbox areas and README. | none |
| `/write/README.txt` | `read` | Explains write surface. | none |
| `/write/inbox-cached` | `mkdir`, `create`, `write`, `flush`, `release` | Stores completed files in local cache and queues `ingest_cached_files`. | queues work; tape writes require later promotion/execution |
| `/write/inbox-cached/<path>` | `unlink` | Removes the cached local file if present. | none |
| `/write/inbox-direct` | write-like operations | Rejected read-only for now. | none |

## Unsupported Mutations

The FUSE surface rejects direct archive mutation. These should be fast failures:

- create/write outside `/write/inbox-cached`
- rename
- remove directories
- truncate
- mknod
- direct write to `/write/inbox-direct`

## Performance Contract

Virtual-only operations should be snappy enough for file managers:

- top-level `stat`, `readdir`, and shallow JSON/README reads should not build the
  full catalog tree
- `stat /system/inventory.json` must not touch the changer
- only reading `/system/inventory.json` is expected to call `mtx`
- only opening readable archived files is expected to queue restore jobs
- only writing into `/write/inbox-cached` is expected to queue ingest jobs
