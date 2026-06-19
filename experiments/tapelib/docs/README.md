# Tapelib Notes

Tapelib is the active TL2000 + dual LTO-5 path for this repo, separate from the
older FossilSafe experiment. The design target is a catalog-backed tape-library
overlay with a FUSE surface and queue-owned hardware actions.

## Implemented Now

- fruit scaffolding under [`fruits/tapelib`](/work/flake/fruits/tapelib)
- manager selection support through `org.storage.tape.manager = "tapelib"`
- `services.tapelib` NixOS module
- `tapelib plan-games-backup` for the current game-archive workflow
- read-only JSON web/status service and small operator console
- persistent SQLite catalog and job-journal schema
- `tapelib retrieve` for manifest-driven copy-out job planning into a chosen
  local destination
- `tapelib run-queue --once` for mounted-only retrieve execution
- `tapelib run-queue --once --auto` and opt-in daemon automatic retrieve
  scheduling for load, read-only mount, copy-out, and release
- `tapelib job-status <job_id>` and per-job FUSE JSON status snapshots
- daemon startup reconciliation for active jobs interrupted by restart
- read-only FUSE surface at `/mnt/tapelib`
- read-only TL2000 inventory using `mtx status`
- journaled operator commands for tape load/unload and LTFS mount/unmount
- `tapelib reconcile-hardware` for matching interrupted jobs to real mount and
  changer state
- `tapelib inventory-manifest` for additive catalog snapshots that can be
  written to LTFS tapes
- cache-budgeted archive staging, LTFS write jobs, per-file catalog commits,
  tape-carried manifests, and `tapelib import-inventory`
- readable FUSE paths that queue retrieve jobs and stream restored cache when
  present
- cached FUSE write inbox ingest that stores closed files locally and queues
  `ingest_cached_files` jobs
- `tapelib promote-ingest` to turn cached inbox jobs into `write_archive` jobs
  for explicit target tapes
- confirmed web action API for inventory refresh, mounted tape indexing,
  verification, retrieve queueing, safe cancel, ingest promotion, and guarded
  hardware load/unload/mount/unmount actions
- `tapelib backup-db` and a daily NixOS timer for online SQLite catalog backups
- `tapelib verify` can now auto-select mounted allowed tapes when `--tape` is
  omitted, which makes the timer-backed verification path usable again
- cache cleanup now tolerates unreadable staged files and continues cleaning the
  rest of the cache instead of failing the whole run
- `games-backup-status` is catalog-only by default; pass `--plan` when you want
  the slower fresh source-tree scan and full current plan
- the FUSE overlay keeps a short in-process metadata cache so repeated virtual
  file-manager probes do not rewalk the catalog on every `readdir`/`getattr`
- FUSE browse/readable deep paths now use scoped SQLite parent/name lookups for
  directory listings and exact row lookups for file metadata, so missing path
  probes do not build the full archive tree

## Still Planned

- automatic tape-set planning for cached FUSE ingest
- bundled-member extraction through readable FUSE paths
- parallel dual-drive queue optimization

The detailed roadmap lives in
[`plan1.txt`](/work/flake/docs/tape-library/tapelib/plan1.txt). It is a
plan, not a description of current behavior, and it keeps the generic tapelib
service separate from the future game archive backup consumer.

Focused operator docs:

- [Filesystem surface](./filesystem/README.md)
- [Filesystem operation matrix](./filesystem/operations.md)
- [Filesystem performance smoke test](./filesystem/performance-smoke-test.md)

The implemented job journal is the first persistent backbone, not the full job
runner yet. It stores job rows and event rows, and daemon startup marks jobs
that were in active hardware-facing states as `needs_operator` so later
reconciliation can inspect mounts, changer state, and open files before moving
tapes.

## SQLite Backbone

The default database path is `/var/lib/tapelib/catalog.sqlite`, configurable
through:

```nix
org.storage.tape.tapelib.database.path = "/var/lib/tapelib/catalog.sqlite";
```

Current tables:

- `tapes`
- `files`
- `jobs`
- `job_events`
- `drives`
- `cache_entries`
- `inventory_snapshots`
- `inventory_observations`

Useful commands:

```bash
tapelib init-db
tapelib create-job inventory_library
tapelib retrieve --manifest wanted.json --dest /home/example/retrieved
tapelib run-queue --once
tapelib run-queue --once --auto
tapelib promote-ingest --job-id <id> --tape 385182L5 --namespace /incoming
tapelib backup-db
tapelib job-status <job_id>
tapelib cancel <job_id>
tapelib jobs
tapelib journal
tapelib reconcile-hardware
tapelib inventory-manifest --output /var/lib/tapelib/status/TAPELIB-INVENTORY.json
tapelib import-inventory /mnt/ltfs/TAPELIB-INVENTORY.json
tapelib games-backup-status
tapelib games-backup-run-next
tapelib filesystem-smoke-test
```

The JSON service exposes the same backbone through `/api/status`, `/api/jobs`,
`/api/journal`, `/api/tapes`, `/api/drives`, `/api/files`, `/api/cache`,
`/api/warnings`, and `/api/console`. The `/` route serves a small operator
console over those endpoints. `POST /api/actions/retrieve` queues restores,
`POST /api/actions/cancel` requires `confirm = "cancel"`, and
`POST /api/actions/promote-ingest` requires `confirm = "promote-ingest"`.

## Game Backup Progress

`tapelib games-backup-status` is the quickest game-library backup progress
check. It prints whether a game archive write is active, which tape has data
written, completed batch counts, the next queued/waiting write, and the current
multi-tape plan.

```bash
tapelib games-backup-status
tapelib games-backup-status --json
tapelib games-backup-status --plan
```

The default status path is intentionally snappy and only reads the job/catalog
state. `--plan` performs a fresh walk of the configured game source roots and is
expected to be slower.

Game backups intentionally run as staged cache waves. A completed wave can leave
no queued `write_archive` job; that is not a hardware failure, it means the
next cache wave has not been staged yet. Stage another wave, then continue the
next queued or interrupted write with:

```bash
tapelib stage-games-backup
tapelib games-backup-run-next --resume
```

If a rebuild or service restart interrupts a write, the job is moved to
`needs_operator` and must be resumed so already written files can be detected
and skipped safely:

```bash
tapelib games-backup-run-next --resume
```

On NixOS, the module also provides a manual systemd wrapper:

```bash
sudo systemctl start tapelib-games-backup-run-next.service
systemctl status tapelib-games-backup-run-next.service --no-pager
journalctl -fu tapelib-games-backup-run-next.service
```

The service is configured with `restartIfChanged = false` and
`stopIfChanged = false` and runs `games-backup-run-next --resume`, so routine
`nixos-rebuild switch` runs should not intentionally restart active game
writes, and interrupted `needs_operator` writes can be resumed by starting the
same service again. Avoid stopping the service mid-write unless you are doing
operator recovery; let the one-batch runner exit after the current queued write
completes.

The runner executes as `services.tapelib.fuse.user` with supplementary
`tapelib` and `tape` groups. That matches the foreground LTFS/cache ownership
used by the game-library workflow while preserving access to the tapelib catalog
and tape devices.

## Web Action API

The operator web service exposes guarded actions at
`POST /api/actions/<action>`. Risky actions require an explicit JSON
`confirm` value equal to the action name, so a single stray click or stale form
cannot load, unload, mount, unmount, index, cancel, or promote by itself.

Implemented actions:

```text
inventory
retrieve
cancel            confirm: cancel
promote-ingest    confirm: promote-ingest
verify            confirm: verify
index-tape        confirm: index-tape
load-tape         confirm: load-tape
unload-tape       confirm: unload-tape
mount-ltfs        confirm: mount-ltfs
unmount-ltfs      confirm: unmount-ltfs
```

Examples:

```bash
curl -sS -X POST http://127.0.0.1:5001/api/actions/index-tape \
  -H 'content-type: application/json' \
  -d '{"target":"drive0","confirm":"index-tape"}'

curl -sS -X POST http://127.0.0.1:5001/api/actions/load-tape \
  -H 'content-type: application/json' \
  -d '{"barcode":"385182L5","drive":"drive0","confirm":"load-tape"}'

curl -sS -X POST http://127.0.0.1:5001/api/actions/verify \
  -H 'content-type: application/json' \
  -d '{"target":"drive0","mode":"metadata","confirm":"verify"}'
```

## FUSE Surface

`tapelib-fuse.service` mounts `/mnt/tapelib` as a catalog-first browser surface
with one cache-backed writable inbox.
The NixOS module also creates a user-home shortcut by default:

```text
/home/example/tapelib -> /mnt/tapelib
```

Set `services.tapelib.fuse.homeLink = null;` to disable that shortcut, or set it
to another absolute path to expose the FUSE mount somewhere else.

The FUSE process caches virtual metadata snapshots briefly:

```nix
services.tapelib.fuse.metadataCacheSeconds = 1.0;
```

This keeps GUI file managers from making every virtual `readdir`/`getattr`
probe rebuild catalog views. Set it to `0` while debugging if every FUSE lookup
must reflect the catalog immediately.
`desktoptoodle` currently overrides this to `15.0` as a temporary cushion while
the catalog browse hot path is being tightened.
Top-level directories, `/system`, `/jobs`, tape roots under `/browse` and
`/readable`, and static virtual files are answered without building the full
catalog tree. Live changer inventory is only read when `/system/inventory.json`
is opened for content, not when a file manager stats the entry.

The current top-level layout is:

```text
/mnt/tapelib/
  README.txt
  browse/
  readable/
  write/
    inbox-cached/
    inbox-direct/
  thumbnails/
  jobs/
  system/
```

Current behavior:

- `browse/<tape>/` is metadata-only and is safe for browsing.
- `readable/<tape>/` queues retrieve jobs for direct catalog entries and streams
  local restored cache when present.
- `write/inbox-cached/` accepts cached writes, stores closed files locally, and
  queues `ingest_cached_files` jobs.
- `write/inbox-direct/` is present but rejects writes.
- `thumbnails/` exposes local placeholder filetype icons and a reserved cached
  thumbnail directory, without touching tapes.
- `jobs/` exposes queue and journal JSON snapshots.
- `system/` exposes inventory, status, config, and per-drive JSON snapshots.

This keeps GUI browsing from accidentally loading or writing a tape. Reads and
writes become queued cache-backed jobs instead of direct hardware operations.

The layers are deliberate. Browsing metadata, reading archived data, and writing
new data have different safety rules on tape hardware. Cached writes become
queued ingest jobs. `tapelib promote-ingest --job-id <id> --tape <barcode>`
promotes one into a normal `write_archive` job for the chosen tape, so the
existing `write-archive` runner can flush it to LTFS once the tape is mounted
read-write.

## Database Backups

`tapelib backup-db` creates an online SQLite backup under the configured backup
directory. The NixOS module exposes:

```nix
services.tapelib.database.backupDir = "/var/lib/tapelib/backups";
```

and wires `tapelib-db-backup.timer` to run daily.

## Retrieve Jobs

`tapelib retrieve` is the copy-out interface for getting archived files back to
a local destination. It does not imply putting files back in their original
source locations.

The first accepted input is a JSON manifest:

```json
{
  "files": [
    "385182L5:/games/foo.zip",
    {
      "tape_barcode": "430550L5",
      "path": "/games/bar.zip"
    }
  ]
}
```

The command:

```bash
tapelib retrieve --manifest wanted.json --dest /home/example/retrieved
```

validates entries against the catalog, groups them by tape, prefers already
loaded tapes first using the current SQLite drive state, and creates a queued
`retrieve_files` job. Output paths preserve tape and archive paths under the
destination, such as:

```text
/home/example/retrieved/385182L5/games/foo.zip
```

Duplicate queued retrieve requests with the same file set and destination join
the existing job. `tapelib cancel <job_id>` can cancel jobs that have not reached
changer-facing states; active hardware-facing jobs are rejected so tape movement
is not interrupted unsafely.

`tapelib run-queue --once [--job-id <job_id>]` is mounted-only by default. It
looks for a queued `retrieve_files` job, verifies that every required tape is
already loaded according to SQLite and that each drive's configured LTFS mount
path is mounted, then copies files from the LTFS mount to the planned
destination. If any tape is not mounted, the job moves to `waiting_for_mount`
and no files are copied. The default mode never loads, mounts, unmounts, or
unloads tapes.

`tapelib run-queue --once --auto` enables the automatic retrieve scheduler for
one job. It prefers already mounted tapes, mounts already loaded tapes read-only,
chooses an empty configured drive for library-resident tapes, uses the existing
locked load/mount helpers, copies the files, and releases tapes it mounted when
it needs that drive for later groups. `tapelibd` can run this same path when
`services.tapelib.scheduler.automaticRetrieve = true`.

During copy-out, tapelib writes to a temporary file beside the final destination
and atomically renames it into place. Existing destination files are accepted
only when their size and, when known, checksum match the catalog; matching files
are journaled as skipped, while different contents still fail conservatively.

Retrieve progress is derived from the durable job journal. `tapelib job-status
<job_id>` prints a JSON snapshot with state, bucket, required tapes, blocked
tapes, copied file count, copied bytes, total bytes, progress percent, and recent
events. The FUSE mount exposes the same shape as:

```text
/mnt/tapelib/jobs/queued/<job_id>.json
/mnt/tapelib/jobs/waiting/<job_id>.json
/mnt/tapelib/jobs/active/<job_id>.json
/mnt/tapelib/jobs/failed/<job_id>.json
/mnt/tapelib/jobs/complete/<job_id>.json
```

The status files are read-only observations. They do not advance the queue or
touch the changer.

## Hardware Inventory

`tapelib inventory` runs:

```bash
mtx -f <changerDevice> status
```

and parses drive state, slot state, import/export slots, and barcodes. The
result is written into SQLite:

- full storage slots become `tapes` rows with `current_location = "slot:<n>"`
- loaded tapes become `current_location = "drive:<driveName>"`
- configured drives are refreshed in the `drives` table with their current
  empty/full state

This operation is read-only against the changer. It does not load, unload, or
move tapes.

L4 media is intentionally ignored by tapelib for now. Inventory still records
L4 barcodes as `ignored_generation`, but normal catalog browsing and hardware
execution default to `L5` only.

## Hardware Execution

Operator commands:

```bash
tapelib load-tape 385182L5 drive0
tapelib mount-ltfs drive0
tapelib unmount-ltfs drive0
tapelib unload-tape drive0
tapelib reconcile-hardware
```

Execution model:

- `load-tape` takes the changer lock and runs `mtx load <slot> <driveIndex>`.
- `unload-tape` takes the changer lock and runs `mtx unload <slot> <driveIndex>`.
- `mount-ltfs` takes the drive lock and runs `ltfs` against the drive SCSI
  generic device.
- `unmount-ltfs` takes the drive lock and runs `fusermount -u`, falling back to
  `umount`.
- each command creates a job row and journal events before hardware actions
- failed commands are marked `failed` with `last_error`

Locks live under `/var/lib/tapelib/locks`.

Raw `mtx`, `ltfs`, and `fusermount` commands are still physically valid, but
they bypass tapelib's locks and journal. Prefer tapelib commands during normal
operation. If manual hardware commands are used, unmount before unloading, then
run `tapelib inventory` and `tapelib reconcile-hardware` so SQLite matches the
real changer and mount state again.

Operator users should be members of the `tapelib` group. The NixOS module sets
the state directory, SQLite database, lock directory, cache paths, and LTFS
mount paths group-writable so CLI commands can update the job journal and
create SQLite WAL files.

The `/mnt/tapelib` mountpoint is prepared by `tapelib-fuse.service`, not
tmpfiles, because the active FUSE mount is intentionally read-only.

## Per-Tape Library Inventory

`tapelib inventory-manifest` emits a `tapelib-library-inventory-v1` JSON
snapshot with tapes, drives, and catalog file entries. The write runner copies
this to participating LTFS tapes as:

```text
/TAPELIB-INVENTORY.json
```

These manifests are additive recovery hints. When a tape later reports what it
believes other tapes contain, `tapelib import-inventory` stores that as a
snapshot and observation set. Older snapshots must never delete newer catalog
rows; if two observations disagree, the most recent observation wins, and direct
indexed or verified catalog rows are not downgraded.

## Game Archive Planning Rules

Current planner assumptions:

- source roots are collapsed across:
  - `/home/example/games/incoming`
  - `/home/example/games/_source-archives`
- default atomic unit for the wishlist archive is the search directory such as
  `wishlist/shared/rabbids`
- `wishlist/shared/best-50-by-console/<console>` is treated as the atomic unit
  instead of the parent folder
- atomic units are packed onto the selected tape list with first-fit decreasing,
  so later smaller units can fill earlier tape gaps before the planner uses
  another tape
- if a unit is larger than one tape, the planner falls back to splitting by
  files and records that split in the plan output
- staging skips logical game files that already exist anywhere in the game
  archive namespace, so a later improved plan does not duplicate already-written
  files on a different tape
- `games.tapeCapacityBytes` is a byte count. The default is
  `1400000000000`, leaving margin below an LTO-5 cartridge's advertised
  1.5 TB decimal uncompressed capacity.

## Inventory Surface

Use host inventory like:

```nix
facts.storage.tape.devices = {
  changer = "/dev/tape/by-id/REPLACE_ME";
  drives = [
    "/dev/tape/by-id/REPLACE_ME"
    "/dev/tape/by-id/REPLACE_ME"
  ];
};

org.storage.tape = {
  manager = "tapelib";
  tapelib = {
    stateDir = "/var/lib/tapelib";
    openFirewall = false;
    games.selectedTapes = [ "385182L5" "430550L5" "383685L5" ];
  };
};
```

Keep changer and drive devices in `facts.storage.tape.devices` as stable
`/dev/tape/by-id/REPLACE_ME
should usually mean attaching the `storage/tape` dendrite and `tapelib` fruit to
that host, copying or restoring `/var/lib/tapelib`, and updating only those
host-local by-id device facts.

Attach the fruit explicitly with:

```nix
fruits = [ "tapelib" ];
```
