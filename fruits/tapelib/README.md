# Tapelib Fruit

This fruit is the active TL2000 tape-library overlay path for this repo. It is
separate from the older FossilSafe experiment and is built around three ideas:

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
- manifest-driven `tapelib retrieve` job creation for copy-out planning into a
  chosen local destination
- explicit mounted-only retrieve execution through `tapelib run-queue --once`
- progress-oriented job snapshots through `tapelib job-status <job_id>` and
  `/mnt/tapelib/jobs/<bucket>/<job_id>.json`
- read-only TL2000 inventory through `mtx status`, persisted into SQLite as
  tape slot/location and drive state records
- journaled operator commands for tape load/unload and LTFS mount/unmount
- additive library inventory manifest rendering for later per-tape backup

Still planned:

- queued retrieve reads from `/mnt/tapelib/readable`
- staged write acceptance under `/mnt/tapelib/write/inbox-cached`
- retrieve execution that loads or mounts tapes automatically
- import of tape-carried inventory manifests
- a write runner that drops manifests onto each written LTFS tape

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

The read-only FUSE surface is mounted by `tapelib-fuse.service`. It is safe for
file-manager browsing: `browse` listings come from SQLite/configured tape names,
and opening archived data files from `browse` is rejected instead of loading a
tape. `readable` paths currently return placeholder metadata until the retrieve
queue runner exists.

`tapelib retrieve --manifest wanted.json --dest /some/local/path` creates or
joins a queued `retrieve_files` job. This is a copy-out operation: it preserves
the archived paths under the chosen destination and does not try to recreate
the files' original source locations. `tapelib cancel <job_id>` only cancels
jobs that have not reached changer-facing states.

`tapelib run-queue --once` performs the first safe execution step for retrieve
jobs. It only copies files when every required tape is already loaded in SQLite
and its configured LTFS mount path is mounted. It does not load, mount, unmount,
or unload tapes. Operators should load and mount media with the explicit
hardware commands first; later scheduler work can automate that path.

`tapelib job-status <job_id>` reads the durable journal and returns a compact
progress snapshot with required tapes, blocked tapes, copied file count, copied
bytes, total bytes, and recent events. The FUSE job buckets expose matching
per-job JSON files so a file browser or terminal can inspect queue state without
starting work.

`tapelib inventory` now queries the configured changer with `mtx status` and
updates the `tapes` and `drives` tables without moving media. The
`tapelib-inventory.timer` refreshes that view periodically.

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
  is the future read-through surface where opening a file queues a retrieve.
- `/mnt/tapelib/write/inbox-cached`
  is the future write surface where drag/drop writes land in the cache first.
- `/mnt/tapelib/write/inbox-direct`
  is reserved for already-safe fast local sources after preflight checks.
- `/mnt/tapelib/thumbnails`
  is local-only thumbnail and filetype-icon space so GUI thumbnailing does not
  force hardware work.

Drag/drop writes should be enabled by making the write inboxes selectively
writable, committing closed files into cache entries, and then letting the job
runner write complete batches to LTFS. That keeps the file-browser experience
simple while avoiding direct slow-source-to-tape streaming and half-written tape
state.

## Library Inventory Manifests

`tapelib inventory-manifest` renders an additive snapshot intended to be written
to every LTFS tape as `/TAPELIB-INVENTORY.json`.

Tape-carried manifests are advisory. Importing an older manifest must not erase
newer catalog knowledge; conflicts resolve by the most recent observation. The
schema now reserves `inventory_snapshots` and `inventory_observations` for that
future import path.
