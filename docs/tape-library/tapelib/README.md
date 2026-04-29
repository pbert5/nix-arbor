# Tapelib Notes

Tapelib is the active TL2000 + dual LTO-5 path for this repo, separate from the
older FossilSafe experiment. The design target is a catalog-backed tape-library
overlay with a FUSE surface and queue-owned hardware actions.

## Implemented Now

- fruit scaffolding under [`fruits/tapelib`](/work/flake/fruits/tapelib)
- manager selection support through `org.storage.tape.manager = "tapelib"`
- `services.tapelib` NixOS module
- `tapelib plan-games-backup` for the current game-archive workflow
- lightweight JSON web/status service scaffold
- persistent SQLite catalog and job-journal schema
- `tapelib retrieve` for manifest-driven copy-out job planning into a chosen
  local destination
- `tapelib run-queue --once` for mounted-only retrieve execution
- `tapelib job-status <job_id>` and per-job FUSE JSON status snapshots
- daemon startup reconciliation for active jobs interrupted by restart
- read-only FUSE surface at `/mnt/tapelib`
- read-only TL2000 inventory using `mtx status`
- journaled operator commands for tape load/unload and LTFS mount/unmount
- `tapelib reconcile-hardware` for matching interrupted jobs to real mount and
  changer state
- `tapelib inventory-manifest` for additive catalog snapshots that can be
  written to LTFS tapes

## Still Planned

- staged cache-to-tape execution
- retrieve execution that loads or mounts tapes automatically
- readable-path reads that queue retrieve/load work
- writable staged ingest through the FUSE mount
- import of tape-carried inventory manifests

The detailed roadmap lives in
[`plan1.txt`](/work/flake/docs/tape-library/tapelib/plan1.txt). It is a
plan, not a description of current behavior, and it keeps the generic tapelib
service separate from the future game archive backup consumer.

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
tapelib job-status <job_id>
tapelib cancel <job_id>
tapelib jobs
tapelib journal
tapelib reconcile-hardware
tapelib inventory-manifest --output /var/lib/tapelib/status/TAPELIB-INVENTORY.json
```

The JSON service exposes the same backbone through `/api/status`, `/api/jobs`,
and `/api/journal`.

## FUSE Surface

`tapelib-fuse.service` mounts `/mnt/tapelib` as a read-only browser surface.
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
- `readable/<tape>/` is present, but queued retrieve reads are still
  placeholders.
- `write/inbox-cached/` and `write/inbox-direct/` are present with README files;
  writes are rejected for now.
- `thumbnails/` exposes local placeholder filetype icons and a reserved cached
  thumbnail directory, without touching tapes.
- `jobs/` exposes queue and journal JSON snapshots.
- `system/` exposes inventory, status, config, and per-drive JSON snapshots.

This satisfies the first file-browser milestone without letting a GUI
accidentally load or write a tape.

The layers are deliberate. Browsing metadata, reading archived data, and writing
new data have different safety rules on tape hardware. The target drag/drop
behavior is to make `write/inbox-cached` writable and cache-backed first; once a
file or folder copy is complete, tapelib can queue a batch write to an LTFS tape
and update the catalog. That preserves the normal file-browser workflow without
pretending the robot and tape drive are a normal low-latency disk.

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

`tapelib run-queue --once [--job-id <job_id>]` is intentionally mounted-only in
the current implementation. It looks for a queued `retrieve_files` job, verifies
that every required tape is already loaded according to SQLite and that each
drive's configured LTFS mount path is mounted, then copies files from the LTFS
mount to the planned destination. If any tape is not mounted, the job moves to
`waiting_for_mount` and no files are copied. The command never loads, mounts,
unmounts, or unloads tapes.

During copy-out, tapelib writes to a temporary file beside the final destination
and atomically renames it into place. Existing destination files are not
overwritten; that policy intentionally stays conservative until resume/overwrite
behavior is designed.

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
snapshot with tapes, drives, and catalog file entries. The write runner should
eventually copy this to every participating LTFS tape as:

```text
/TAPELIB-INVENTORY.json
```

These manifests are additive recovery hints. When a tape later reports what it
believes other tapes contain, the importer should store that as a snapshot and
observation set. Older snapshots must never delete newer catalog rows; if two
observations disagree, the most recent observation wins.

## Game Archive Planning Rules

Current planner assumptions:

- source roots are collapsed across:
  - `/home/example/games/incoming`
  - `/home/example/games/_source-archives`
- default atomic unit for the wishlist archive is the search directory such as
  `wishlist/shared/rabbids`
- `wishlist/shared/best-50-by-console/<console>` is treated as the atomic unit
  instead of the parent folder
- units are packed onto the selected tape list in order
- if a unit is larger than one tape, the planner falls back to splitting by
  files and records that split in the plan output

## Inventory Surface

Use host inventory like:

```nix
org.storage.tape = {
  manager = "tapelib";
  tapelib = {
    stateDir = "/var/lib/tapelib";
    openFirewall = false;
    games.selectedTapes = [ "385182L5" "430550L5" "383685L5" ];
  };
};
```

Attach the fruit explicitly with:

```nix
fruits = [ "tapelib" ];
```
