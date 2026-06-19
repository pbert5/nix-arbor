# Tapelib Fruit

Archived experiment.

This was the TL2000 tape-library overlay path for this repo. It is preserved
under `experiments/tapelib/` for reference and possible future restart, but it
is not imported by the main flake, not registered as an active fruit, and not
selected by `desktoptoodle`.

The historical operator docs that used to live under `docs/tape-library/tapelib/`
are archived in [`docs/`](./docs/).

It is separate from the older FossilSafe experiment and is built around three
ideas:

- LTFS tapes remain self-contained and recoverable on their own.
- A local catalog database provides fast browse/search without loading tapes.
- Slow or risky hardware work is queued behind a daemon instead of being hidden
  behind direct filesystem access.

## Current Status

Implemented in this repo change:

- a first-class `tapelib` fruit and NixOS module
- declarative service options under `services.tapelib`
- a Python CLI package with:
  - `tapelib init-db`
  - `tapelib inventory`
  - `tapelib status`
  - `tapelib create-job`
  - `tapelib retrieve`
  - `tapelib cancel`
  - `tapelib run-queue`
  - `tapelib job-status`
  - `tapelib jobs`
  - `tapelib journal`
  - `tapelib load-tape`
  - `tapelib unload-tape`
  - `tapelib mount-ltfs`
  - `tapelib unmount-ltfs`
  - `tapelib reconcile-hardware`
  - `tapelib inventory-manifest`
  - `tapelib mount-fuse`
  - `tapelib plan-games-backup`
  - `tapelib daemon`
  - `tapelib serve-web`
- a first-pass multi-tape planner for the game-archive workflow described in
  the host notes
- persistent SQLite schema initialization for tapes, files, jobs, job events,
  drives, and cache entries
- startup recovery that marks jobs interrupted in active states as
  `needs_operator`
- a read-only FUSE browser surface at `/mnt/tapelib` with `browse`,
  `readable`, `write`, `thumbnails`, `jobs`, and `system` top-level folders
- opt-in small-file tar bundling for archive writes, with bundled-member preview
  metadata exposed back through the catalog and FUSE browse surface
- manifest-driven `tapelib retrieve` job creation for copy-out planning into a
  chosen local destination
- explicit mounted-only retrieve execution through `tapelib run-queue --once`
- opt-in automatic retrieve execution through `tapelib run-queue --once --auto`
  and `scheduler.automaticRetrieve`, including load, read-only mount, copy-out,
  and release of scheduler-mounted tapes
- progress-oriented job snapshots through `tapelib job-status <job_id>` and
  `/mnt/tapelib/jobs/<bucket>/<job_id>.json`
- read-only TL2000 inventory through `mtx status`, persisted into SQLite as
  tape slot/location and drive state records
- journaled operator commands for tape load/unload and LTFS mount/unmount
- cache-budgeted archive staging, LTFS write jobs, per-file catalog commits,
  tape manifests, and additive tape-carried inventory import/export
- readable FUSE paths that queue retrieve jobs and stream restored cache when
  present
- cached FUSE write inbox ingest that stores closed files locally and queues
  `ingest_cached_files` jobs
- `tapelib promote-ingest` to turn cached inbox jobs into `write_archive` jobs
  for explicit target tapes
- web operator console endpoints for tapes, drives, files, cache, warnings,
  jobs, and journal, plus confirmed actions for retrieve, cancel, ingest
  promotion, mounted tape indexing, verification, and guarded
  load/unload/mount/unmount
- `tapelib backup-db` and a daily NixOS timer for online SQLite catalog backups
- unattended verify runs now auto-select mounted allowed tapes when `--tape` is
  omitted, so the timer can verify the currently mounted LTFS media
- cache cleanup now skips unreadable staged files instead of failing the whole
  maintenance run

Still planned:

- automatic tape-set planning for cached FUSE ingest
- bundled-member extraction through readable FUSE paths
- parallel dual-drive retrieve/write scheduling

## Layout

- `flake.nix`
  Fruit-local flake for package builds and a focused dev shell
- `nix/tapelib-package.nix`
  Python package build for the `tapelib` CLI and daemon scaffold
- `nix/tapelib-module.nix`
  NixOS module that renders `config.json`, creates services, and wires timers
- `src/tapelib/`
  CLI, SQLite catalog/journal layer, planner, and lightweight daemon/web server
  scaffold

## Usage

```bash
nix develop ./fruits/tapelib
nix build ./fruits/tapelib#tapelib
```

The primary system flake can attach this fruit through `inventory/hosts.nix`
using `fruits = [ "tapelib" ];` plus `org.storage.tape.manager = "tapelib";`
once you are ready to promote it onto a host.

On NixOS, `tapelibd.service` and `tapelib-web.service` run
`tapelib init-db` before startup. The default database path is
`/var/lib/tapelib/catalog.sqlite`.

The FUSE surface is mounted by `tapelib-fuse.service`. It is safe for
file-manager browsing: `browse` listings come from SQLite/configured tape names,
and opening archived data files from `browse` is rejected instead of loading a
tape. Opening direct catalog entries under `readable` queues retrieve jobs into
the local restore cache and returns JSON status until the cache file is ready.
Once restored, repeated reads stream the cached file.
By default the NixOS module also creates a user-home shortcut from
`/home/${services.tapelib.fuse.user}/tapelib` to the FUSE mount point, matching
the existing game-library home shortcut pattern. Set
`services.tapelib.fuse.homeLink = null;` to disable it.

When small-file bundling is enabled, tapelib writes a tar archive plus a bundle
member manifest onto LTFS and stores the bundled member list in SQLite. The
FUSE `browse` tree then previews those member paths as synthetic catalog
entries, while `readable` returns a structured note pointing at the backing tar
bundle until queued extraction support exists.

`tapelib retrieve --manifest wanted.json --dest /some/local/path` creates or
joins a queued `retrieve_files` job. This is a copy-out operation: it preserves
the archived paths under the chosen destination and does not try to recreate
the files' original source locations. `tapelib cancel <job_id>` only cancels
jobs that have not reached changer-facing states.

`tapelib games-backup-status` prints the operator-friendly progress report for
the configured game-library backup, including a clear active/inactive line,
completed game archive batches, the next queued or waiting write, and the full
current tape plan. Use `--json` for automation or `--no-plan` when you want to
skip the fresh source scan.

`tapelib games-backup-run-next --resume` runs the oldest runnable staged
game-library `write_archive` job, including interrupted `needs_operator` jobs
where already written files should be detected and skipped safely. On NixOS,
`tapelib-games-backup-run-next.service` wraps that command as a manual service
with rebuild-resistant change handling for long tape writes. The service runs as
`services.tapelib.fuse.user` with supplementary `tapelib` and `tape` groups so
it can read the foreground cache, write the LTFS mount, and update the catalog.

`tapelib run-queue --once` performs the first safe execution step for retrieve
jobs. By default it only copies files when every required tape is already loaded
in SQLite and its configured LTFS mount path is mounted. It does not move media
in the default mode.

`tapelib run-queue --once --auto` enables the automatic retrieve scheduler for
one job. It prefers already mounted tapes, mounts already loaded tapes read-only,
chooses an empty configured drive for library-resident tapes, calls the existing
locked load/mount helpers, copies the requested files, and releases tapes it
mounted when it needs the drive for later groups. The daemon can run the same
path when `services.tapelib.scheduler.automaticRetrieve = true`.

Retrieve reruns are resumable at the destination-file level: if a destination
already exists with the expected size and, when known, checksum, tapelib records
it as skipped rather than overwriting it.

`tapelib job-status <job_id>` reads the durable journal and returns a compact
progress snapshot with required tapes, blocked tapes, copied file count, copied
bytes, total bytes, and recent events. The FUSE job buckets expose matching
per-job JSON files so a file browser or terminal can inspect queue state without
starting work.

`tapelib inventory` now queries the configured changer with `mtx status` and
updates the `tapes` and `drives` tables without moving media. The
`tapelib-inventory.timer` refreshes that view periodically.

`tapelib verify` accepts `--tape <barcode|drive>` for targeted runs, or with no
explicit tape it verifies every mounted LTFS tape whose barcode generation is
allowed by the current config. That keeps the systemd timer usable without
hard-coding a single drive name.

## Hardware Commands

The first hardware execution commands are explicit operator actions:

```bash
tapelib load-tape 385182L5 drive0
tapelib mount-ltfs drive0
tapelib unmount-ltfs drive0
tapelib unload-tape drive0
tapelib reconcile-hardware
```

Each command creates a persisted job, writes journal events before risky
hardware actions, uses locks under `/var/lib/tapelib/locks`, and marks the job
`complete` or `failed`.

Direct `mtx`, `ltfs`, and `fusermount` commands still work at the hardware
level, but they bypass tapelib's SQLite state, job journal, and lock files. Use
tapelib commands for normal operation. If you do move media manually, unmount
LTFS first, then run `tapelib inventory` and `tapelib reconcile-hardware` so the
catalog can catch up before another queued operation starts.

Operator commands are intended to be run by users in the `tapelib` group. The
NixOS module keeps `/var/lib/tapelib`, the SQLite database, lock files, mount
paths, and cache paths group-writable so SQLite WAL files and hardware locks can
be created outside the systemd service.

The `/mnt/tapelib` mountpoint is prepared by `tapelib-fuse.service` instead of
tmpfiles because tmpfiles cannot chmod it while the read-only FUSE mount is
active.

By default, tapelib only operates on `L5` barcode generations:

```nix
services.tapelib.library.allowedGenerations = [ "L5" ];
```

L4 tapes seen by inventory are recorded as ignored media and are not shown in
the normal FUSE browse surface.

## File Browser Model

The mount is intentionally layered because tape is not a random-access disk:

- `/mnt/tapelib/browse`
  is metadata-only and never loads tapes.
- `/mnt/tapelib/readable`
  queues retrieve jobs for direct catalog entries and streams local restored
  cache when present.
- `/mnt/tapelib/write/inbox-cached`
  accepts cached writes, stores closed files locally, and queues ingest jobs.
- `/mnt/tapelib/write/inbox-direct`
  is reserved for already-safe fast local sources after preflight checks.
- `/mnt/tapelib/thumbnails`
  is local-only thumbnail and filetype-icon space so GUI thumbnailing does not
  force hardware work.

Drag/drop writes land in the local cache first and create queued
`ingest_cached_files` jobs plus `cache_entries`. Promote one into a tape write
queue with:

```bash
tapelib promote-ingest --job-id <id> --tape 385182L5 --namespace /incoming
```

That produces a normal `write_archive` job. No tape moves just because a file
was copied into the inbox.

## Database Backups

`tapelib backup-db` creates an online SQLite backup under
`services.tapelib.database.backupDir`, defaulting to `/var/lib/tapelib/backups`.
The NixOS module wires `tapelib-db-backup.timer` to run it daily.

## Small-file tar bundling

Archive writes can optionally bundle many tiny files into tar archives before
they are flushed to LTFS. This reduces small-file write churn on the tape while
keeping a preview of the bundled members available through the tapelib catalog.

Enable it through the NixOS module:

```nix
services.tapelib.archive.smallFileBundleMaxBytes = "8M";
services.tapelib.archive.smallFileBundleTargetBytes = "256M";
```

With the default `smallFileBundleMaxBytes = "0"`, bundling is disabled and
tapelib keeps writing files directly to LTFS as before.

## Library Inventory Manifests

`tapelib inventory-manifest` renders an additive snapshot intended to be written
to every LTFS tape as `/TAPELIB-INVENTORY.json`.

Tape-carried manifests are advisory. Importing an older manifest must not erase
newer catalog knowledge; conflicts resolve by the most recent observation.
`tapelib import-inventory <drive|barcode|mount|file>` stores snapshots and
observations, imports missing advisory rows, and does not downgrade direct
indexed or verified catalog rows.
