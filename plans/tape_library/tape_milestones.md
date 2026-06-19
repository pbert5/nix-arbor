I checked the `distribuited-file-store` branch and the current `fruits/tapelib` state. The old pasted plan is still the right “north star” for the system: catalog-backed FUSE overlay, queue-owned hardware work, dual LTO-5 drives, shared changer lock, LTFS tapes remaining self-contained, staged writes, and multi-tape archive planning. 

The repo has already moved past pure planning. Current implementation includes the `tapelib` fruit, NixOS module, SQLite catalog/job schema, read-only FUSE browser, TL2000 inventory through `mtx status`, manual load/unload/mount/unmount commands, retrieve job creation, mounted-only retrieve execution, opt-in automatic retrieve loading/mounting, readable-path queued retrieves, writable cached FUSE ingest with explicit archive promotion, job-status snapshots, a web/operator console with guarded actions, cache-budgeted archive staging, LTFS write jobs, tape-carried manifest export/import, SQLite catalog backups, and a game-backup planner. The main remaining gaps are deeper verification/scrub workflows, parallel dual-drive optimization, and production hardening.
## Implementation Status

Last updated: 2026-04-29

| Milestone | Status | Notes |
|-----------|--------|-------|
| 0. Stabilize baseline | ✅ Done | tests pass, nix build clean |
| 1. Catalog indexing | ✅ Done | `tapelib index-tape` + `db.index_tape()` |
| 2. Safe manual workflow | ✅ Done | `tapelib doctor` + hardened preflight checks |
| 3. Mounted-only retrieve MVP | ✅ Done | `tapelib retrieve` + `run-queue`; reruns now skip already-copied matching destinations |
| 4. Automatic retrieve scheduler | 🔄 Partial | `tapelib run-queue --once --auto` can load, mount, copy, and release scheduler-mounted tapes; `tapelibd` can run it when `scheduler.automaticRetrieve = true` |
| 5. Cache/staging manager | ✅ Done | rolling cache-budget staging, reservation checks, real `cleanup-cache`, permission-tolerant maintenance cleanup |
| 6. Archive/write planning | ✅ Done | `tapelib stage-games-backup` fills cache-budget waves and skips already-written / queued files for safe refill |
| 7. LTFS write runner | ✅ Done | `tapelib write-archive`, incremental cache drain + per-file catalog commits, aggregated tape manifests, tape-carried inventory export |
| 8. Writable FUSE ingest | 🔄 Partial | `/write/inbox-cached` stores closed files in local cache, queues `ingest_cached_files`, and `promote-ingest` turns them into `write_archive` jobs for explicit target tapes |
| 9. Readable FUSE retrieve | 🔄 Partial | `/readable/<tape>/<path>` queues retrieve jobs and streams restored cache when present; bundled extraction remains planned |
| 10. Tape-carried inventory import | ✅ Done | `tapelib import-inventory` stores snapshots + advisory observations |
| 11. Verification and scrubbing | 🔄 Partial | `tapelib verify [--tape <barcode|drive>] [--mode metadata|checksums]`, timer-safe auto-selection of mounted allowed tapes, and confirmed web `verify` action |
| 12. Web/API operator console | 🔄 Partial | read-only `/` console plus `/api/console`, tapes, drives, files, cache, warnings, jobs, journal; POST actions for inventory, retrieve, safe cancel, and ingest promotion |
| 13. Dual-drive queue optimization | ❌ Not started | |
| 14. Production hardening | 🔄 Partial | `tapelib backup-db` plus daily `tapelib-db-backup.timer`; migration/versioning and metrics remain planned |

---
## Milestones to “fully functional”

### 0. Stabilize the current baseline

Goal: make the current branch safe to develop against.

What exists already:

* NixOS module and service wiring
* CLI package
* DB initialization
* read-only FUSE browser
* manual hardware commands
* mounted-only retrieve path

Needed:

* Add a fake/simulated changer backend for tests.
* Add tests for:

  * `mtx status` parsing
  * DB migration/init
  * retrieve manifest validation
  * job state transitions
  * FUSE browse tree generation
* Verify Nix build/dev shell/package commands work cleanly.

Acceptance check:

* `nix build ./fruits/tapelib#tapelib`
* `tapelib init-db`
* tests pass without real tape hardware
* fake inventory can populate tapes/drives/jobs

---

### 1. Catalog indexing from real LTFS tapes

Goal: mounted LTFS tapes can be scanned into the catalog.

Right now, the DB schema has `tapes`, `files`, `jobs`, `job_events`, `drives`, `cache_entries`, and inventory snapshot tables.  But the system still needs a real `index_tape` runner that walks a mounted LTFS filesystem and records files.

Needed:

* `tapelib index-tape <barcode|drive>`
* Detect mounted drive path.
* Walk LTFS contents.
* Insert/update `files` rows:

  * tape ID
  * path
  * size
  * mtime
  * optional checksum
  * state: `known`, `indexed`, `verified`, etc.
* Ignore internal files like:

  * `/TAPELIB-INVENTORY.json`
  * temporary write files
  * LTFS metadata artifacts, if exposed
* Mark missing old files as `missing_after_reindex` instead of silently deleting.

Acceptance check:

* Load/mount a tape.
* Run `tapelib index-tape drive0`.
* `/mnt/tapelib/browse/<barcode>/...` shows real files from SQLite without touching the tape.
* Reindexing after a file disappears marks it suspicious rather than erasing history.

---

### 2. Safe manual operator workflow

Goal: before automation, the manual path should be reliable enough to use.

The executor already wraps `mtx load`, `mtx unload`, `ltfs`, and `fusermount/umount` with job rows, journal events, and lock files. 

Needed:

* Harden preflight checks:

  * refuse unload if LTFS is still mounted
  * refuse mount if drive empty
  * refuse load if drive full
  * refuse write mount unless job type requires it
* Improve `reconcile-hardware`:

  * compare DB drive state to `mtx status`
  * compare mounted paths to `findmnt`
  * mark mismatches as `needs_operator`
* Add “safe recovery” command:

  * `tapelib doctor`
  * reports mounted tapes, DB state, changer state, active jobs, stale locks

Acceptance check:

* Pull power or kill service during a load/mount operation.
* Restart daemon.
* Job becomes `needs_operator`.
* `tapelib reconcile-hardware` can prove completion or ask for human action.

---

### 3. Mounted-only retrieve MVP

Goal: make restore work reliably when the operator has already loaded and mounted the required tapes.

This is partly implemented. `tapelib retrieve --manifest ... --dest ...` queues a `retrieve_files` job, and `tapelib run-queue --once` copies only if all required tapes are already mounted. 

Needed:

* Resume behavior:

  * skip already copied files if checksum/size matches
  * fail or require flag if destination differs
* Per-file copy status in DB or job events.
* Optional checksum verification after copy.
* Better partial temp cleanup.
* Folder retrieve manifest generation from catalog paths.

Acceptance check:

* Create manifest with files from one mounted tape.
* Run retrieve.
* Files copy to destination atomically.
* Re-running does not duplicate or corrupt output.
* Job-status shows real progress.

---

### 4. Automatic retrieve scheduler

Goal: restore jobs should load, mount, copy, and optionally unload tapes automatically.

This is now partially implemented. The default queue runner is still mounted-only
for operator safety, but `tapelib run-queue --once --auto` can take a queued retrieve
job through load, read-only LTFS mount, copy-out, and release of tapes that it
mounted itself. `tapelibd` can run that automatic path when
`scheduler.automaticRetrieve = true`.

Needed:

* Real scheduler loop in `tapelibd`:

  * find queued jobs ✅
  * group by tape ✅
  * prefer already mounted tapes ✅
  * choose free drive ✅
  * acquire changer lock only for movement ✅ through existing `executor.load_tape`
  * acquire drive lock for mount/read/unmount ✅ through existing executor mount/unmount commands
* State transitions:

  * `queued` ✅
  * `waiting_for_drive` ✅
  * `waiting_for_changer` ✅
  * `loading_tape` ✅
  * `mounting_ltfs` ✅
  * `running` ✅
  * `unmounting` ✅
  * `unloading` ✅
  * `complete` ✅
* Idle-mounted tape policy:

  * keep recently used tape mounted for N minutes
  * do not unload while file handles/jobs exist
  * current behavior leaves the final scheduler-mounted tape mounted by default,
    or unloads it when `scheduler.unloadAfterRetrieve = true`
* Two-drive policy:

  * one drive can restore while the changer loads another tape into the second drive
  * changer remains single-operation locked
  * current behavior is sequential; full parallel dual-drive preparation remains
    planned for milestone 13

Acceptance check:

* Queue retrieve job for files across two tapes.
* No manual load commands. ✅ with `run-queue --once --auto` or daemon automatic mode
* System loads tape A, restores its files, then handles tape B. ✅ sequentially
* With two drives, it can keep tape A mounted while preparing tape B when safe. Planned under dual-drive optimization.

---

### 5. Cache/staging manager

Goal: writes never stream directly from slow NFS or random sources to tape unless explicitly allowed.

The Nix module already has cache config options like cache path, max size, and reserved free bytes.  But the actual cache lifecycle still needs to be implemented.

Needed:

* Cache directory layout:

  * `staging/archive-jobs`
  * `restore-jobs`
  * `spool/write-bundles`
  * `temp/partial`
  * `manifests`
* Cache reservation:

  * check free space
  * reserve bytes for job
  * prevent overcommit
* Staging copy:

  * source to cache
  * checksum
  * file closed/complete marker
* Cleanup:

  * remove failed partials
  * keep completed bundles until verified
  * respect reserved free space
* Implement the module’s `cleanup-cache` command, since the timer is already wired but the functionality still needs to be real. 

Acceptance check:

* Stage 100 GB from NFS to local cache.
* Killing the process mid-copy leaves recoverable partial state.
* Restart continues or safely discards partials.
* Tape write never starts until the full batch is staged.

---

### 6. Archive/write planning

Goal: turn selected source data into a durable multi-tape write plan.

The game archive planner already exists as a first pass, with source roots collapsed from `incoming` and `_source-archives`, atomic wishlist/search-folder units, and ordered tape packing. 

Needed:

* Promote planner output into DB-backed `archive_dataset` jobs.
* Track:

  * logical namespace
  * source roots
  * planned files
  * assigned tape
  * estimated size
  * checksum status
  * split-unit metadata
* Generalize beyond games:

  * `tapelib plan-archive --source ... --namespace ... --tapes ...`
* Add dry-run reports:

  * per-tape used/free estimate
  * split units
  * files too large
  * missing source roots
  * expected cache need

Acceptance check:

* Plan archive larger than one tape.
* Planner produces deterministic tape assignments.
* Atomic units are not split unless they exceed one tape.
* Plan can be saved and resumed later.

---

### 7. LTFS write runner

Goal: actually write staged batches to LTFS tapes.

This is probably the biggest “be careful” milestone.

Needed:

* `flush_staging_to_tape` job runner.
* Mount target tape read-write.
* Write only from local cache.
* Use temp names during write:

  * e.g. `.tapelib-writing/<job>/<file>.partial`
* Rename into final LTFS location after successful copy.
* Write tape-local metadata:

  * `/TAPE-MANIFEST.json`
  * `/TAPE-MANIFEST.csv`
  * `/TAPE-CHECKSUMS.sha256`
  * `/README-THIS-TAPE.txt`
  * `/TAPELIB-INVENTORY.json`
* Update catalog only after successful write.
* Optional verify read after write.
* Never interrupt active write except hard failure.

Acceptance check:

* Stage a small archive batch.
* Write it to a scratch LTFS tape.
* Unmount tape.
* Mount tape manually outside tapelib.
* Files and manifest are readable without tapelib.
* Reimport/reindex rebuilds the catalog.

---

### 8. Writable FUSE ingest

Goal: file-browser drag/drop becomes useful without pretending tape is a normal disk.

This is now partially implemented. `/mnt/tapelib/write/inbox-cached` accepts
cached writes through FUSE create/write/flush/release, stores closed files under
the local cache, and queues `ingest_cached_files` jobs. `tapelib promote-ingest`
turns one of those jobs into a normal `write_archive` job only after an operator
chooses a target tape. `/browse` remains metadata-only, and
`/write/inbox-direct` still rejects writes.

Needed:

* Make only `/mnt/tapelib/write/inbox-cached` writable. ✅
* Implement create/write/flush/release in FUSE. ✅
* Store incoming data in local cache, not tape. ✅
* Detect closed files/folders and create ingest records. ✅
* Let user choose target policy:

  * default archive namespace ✅ current target uses the configured namespace
  * selected tape set 🔄 explicit target tape is implemented; automatic tape-set planning remains planned
  * queue only, do not immediately write ✅
* Reject unsafe direct writes by default. ✅
* Keep `/browse` safe and metadata-only. ✅

Acceptance check:

* Drag a folder into `write/inbox-cached`. 🔄 create/write/release and mkdir are implemented; rename-heavy GUI copies still need hardening.
* Files land in cache. ✅
* A queued archive job appears. ✅ after explicit `promote-ingest --job-id ... --tape ...`
* No tape moves until scheduler accepts the job. ✅
* Interrupted copy does not create a half-valid archive job.

---

### 9. Readable FUSE retrieve

Goal: opening files under `/mnt/tapelib/readable/<tape>/...` can trigger safe retrieval.

This is now partially implemented. Direct catalog entries under `readable` queue
retrieve jobs into the local restore cache and return JSON status until the
restored file is present. Once the cache file matches the cataloged size,
repeated reads stream from local cache. Bundled-member extraction still returns
a clear not-implemented JSON response.

Needed:

* Decide exact behavior:

  * option A: opening a file queues a retrieve and returns `EAGAIN`/clear error until ready ✅ implemented as JSON status
  * option B: opening blocks until retrieved
  * option C: opening creates a local cached restore and then streams it ✅ once restored cache is present
* Strongly recommend:

  * no automatic load from `browse` ✅
  * `readable` can queue but not silently move hardware unless config allows it ✅
  * file-manager thumbnailers should not trigger tape movement ✅
* Add xattrs or sidecar JSON:

  * tape barcode ✅ returned in JSON status
  * archive path ✅ returned in JSON status
  * restore status ✅ job id/state returned in JSON status
  * cache status ✅ returned in JSON status

Acceptance check:

* `cat /mnt/tapelib/readable/TAPE/foo.zip` either queues a restore safely or gives a clear “queued, check jobs” message. ✅
* GUI browsing does not accidentally load tapes. ✅
* Repeated reads reuse local restored cache if policy allows. ✅

---

### 10. Tape-carried inventory import

Goal: each tape can help reconstruct the whole library catalog.

The current code can render `TAPELIB-INVENTORY.json`, and the schema reserves `inventory_snapshots` and `inventory_observations`. 

Needed:

* `tapelib import-inventory <mounted tape|file>`
* Parse `/TAPELIB-INVENTORY.json`.
* Store snapshot row.
* Store observation rows.
* Merge additively:

  * never delete newer local knowledge from older tape manifest
  * newest observation wins on conflicts
* Mark confidence/source:

  * directly indexed from tape
  * imported from another tape’s manifest
  * operator-provided
  * stale

Acceptance check:

* Start with empty DB.
* Mount one tape containing `TAPELIB-INVENTORY.json`.
* Import manifest.
* Catalog can show known tapes/files as advisory records.
* Later direct indexing of real tape overrides advisory data.

---

### 11. Verification and scrubbing

Goal: know whether catalog entries are actually recoverable.

The module wires a `tapelib-verify` timer, the CLI can verify mounted allowed
tapes by metadata or checksum, and the web action API exposes a confirmed
`verify` action.

Needed:

* `verify_tape` ✅ mounted tape verification is available through CLI and web action
* `verify_file`
* `verify_archive_job`
* Modes:

  * metadata-only exists check
  * checksum selected files
  * full tape checksum
* Record:

  * `last_verified_at`
  * checksum status
  * read errors
  * media warnings
* Surface warnings in:

  * CLI ✅ writes `status/verify.json` and prints the verification payload
  * FUSE `/system`
  * web UI 🔄 web action exists; richer console rendering remains planned

Acceptance check:

* Verify one tape.
* Correct files become `verified`.
* Missing/unreadable files become `read_error` or `missing_after_reindex`.
* Status clearly tells which tape/file needs attention.

---

### 12. Web/API operator console

Goal: make it usable without remembering every command.

This now has a read-only operator console plus the controlled action API.
`/` serves a small browser console, and `/api/console`, `/api/tapes`,
`/api/drives`, `/api/files`, `/api/cache`, `/api/warnings`, `/api/jobs`, and
`/api/journal` expose the current state. `POST /api/actions/...` supports
inventory refresh, mounted tape indexing, retrieve queueing, safe cancel, ingest
promotion, verification, and guarded load/unload/mount/unmount.

Needed:

* Read-only first:

  * tapes ✅
  * slots ✅ through inventory endpoint
  * drives ✅
  * mounted state 🔄 drive state is exposed; live mount probing is still stronger in CLI/FUSE
  * jobs ✅
  * journal ✅
  * cache usage ✅
  * warnings ✅
* Then controlled actions:

  * inventory ✅
  * index tape ✅ requires `confirm = "index-tape"`
  * retrieve ✅
  * cancel queued job ✅ requires `confirm = "cancel"`
  * promote cached ingest ✅ requires `confirm = "promote-ingest"`
  * verify mounted tape ✅ requires `confirm = "verify"`
  * load/unload with confirmation ✅ requires `confirm = "load-tape"` or `confirm = "unload-tape"`
  * mount/unmount with confirmation ✅ requires `confirm = "mount-ltfs"` or `confirm = "unmount-ltfs"`
* For risky operations, require explicit confirmation:

  * unload ✅
  * write
  * cancel active job
  * force reconcile

Acceptance check:

* Open web UI. ✅
* See current TL2000 state. 🔄 read-only catalog/drive/cache/job state is visible; live changer inventory remains JSON API-backed.
* Queue a retrieve. ✅ through the web action API
* Watch state move through scheduler. 🔄 console refreshes job state; richer per-job web view remains planned
* No destructive/risky action happens from a single accidental click. ✅ guarded
  hardware actions require matching confirmation strings, and no web write action
  is exposed yet.

---

### 13. Dual-drive queue optimization

Goal: fully exploit the TL2000 with two LTO-5 drives while respecting the shared robot.

Needed:

* Drive assignment strategy:

  * read jobs can share mounted read-only tape
  * write jobs require exclusive mounted tape
  * prefer mounted tapes
  * minimize robot moves
* Changer lock:

  * only held during `mtx load/unload/move/inventory`
  * released while drive reads/writes
* Drive locks:

  * held during mount/unmount/write
  * read concurrency policy explicit
* Anti-interruption:

  * never unload tape with active file handles
  * never cancel active write unless forced recovery
  * all active jobs recover to `needs_operator` on crash

Acceptance check:

* Queue jobs requiring two different tapes.
* One drive reads while the other drive is being prepared.
* Changer never receives overlapping commands.
* Scheduler does not unload active tapes.

---

### 14. Production hardening

Goal: make it boring enough to trust.

Needed:

* SQLite migrations instead of only `CREATE TABLE IF NOT EXISTS`.
* Structured config validation.
* Better CLI errors.
* Log rotation.
* Metrics:

  * queue depth
  * active jobs
  * loaded tapes
  * cache free space
  * last inventory
  * last verify
* Prometheus/Grafana optional.
* Backup DB automatically:

  * before schema migration
  * after major write jobs
  * periodically to cache and maybe to tape manifests ✅ daily timer exists
* Permissions audit:

  * `tapelib` group can operate
  * no world-writable mount/cache paths
  * raw hardware access minimized

Acceptance check:

* Reboot host mid-idle.
* Reboot host mid-mounted tape.
* Kill daemon mid-job.
* Fill cache near limit.
* Remove a tape manually.
* System gives recoverable, understandable states.

---

## Suggested ordering

### Phase A: “usable operator tool”

Do these first:

1. Baseline tests/simulation
2. Catalog indexing
3. Safe manual workflow
4. Mounted-only retrieve polish
5. Tape inventory manifest export/import basics

At the end of this phase, you can manually load/mount/index/retrieve tapes safely.

### Phase B: “actual automatic library”

Then:

6. Automatic retrieve scheduler
7. Cache/staging manager
8. Archive/write planning
9. LTFS write runner
10. Verification

At the end of this phase, tapelib can restore and archive through queued jobs without you micromanaging every tape move.

### Phase C: “nice overlay system”

Finally:

11. Writable FUSE ingest
12. Readable FUSE retrieve
13. Web UI
14. Dual-drive optimization
15. Production hardening

At the end of this phase, it behaves like the thing you described: a safe LTFS library overlay where the catalog is browsable, reads/writes become queued jobs, the two drives are used intelligently, and every tape remains self-describing outside the system.

My main recommendation: do **indexing before write support**. Once indexing is solid, every later feature has a truth source to compare against. Then do automatic retrieve before automatic write, because retrieve exercises the scheduler/load/mount path without risking new tape contents.
