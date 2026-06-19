# Modern Tape Backup Plan

This is the modern tape backup plan for this repo.

Use this plan when you mean the current game-library tape workflow.

## Modern Means

- Host: `t320-0`
- Library: Dell TL2000 / IBM `3573-TL`
- Drives: dual IBM `ULT3580-HH5`
- Media target: LTFS on `L5` tapes
- Primary operator surface: `backupper`
- Primary plan: `game_backup`
- Hardware control: `mtx`, `mt1`, `mt2`, `changer-default`, `tape-default`,
  `tape-default-2`, `ltfs-default`, `ltfs-default-2`
- Planning model: the staged game-backup plan that was designed alongside
  `tapelib`, promoted into the active `backupper` workflow without reviving the
  archived `tapelib` services
- Backup payload scope: archive files from `_source-archives` and `incoming`
- Loose `roms` scope: audited for zip-archive coverage, not treated as the
  primary tape payload

## Modern Command Surface

The modern way to run the game-library backup is:

```bash
backupper start game_backup
```

To explicitly retry tapes or jobs that were moved into `needs_operator` or
`failed`, use:

```bash
backupper resume game_backup
```

To run every declarative backupper plan present on the machine:

```bash
backupper start
```

The active declarative plan now lives at
[`inventory/storage/backup-plans/game_backup.nix`](/work/flake/inventory/storage/backup-plans/game_backup.nix).

The service behind it is `backupper-game_backup.service`.

## Current Tape Set

The current active rotation for the modern plan is:

- `383685L5`
- `384933L5`
- `384333L5`

Overflow `L5` tapes remain available behind that core set.

`430550L5` was recovered enough to mount with LTFS and accept a tiny probe
write, but it failed again on the first sustained archive write and is back
out of the active rotation pending deeper media or drive-path investigation.

`385182L5` is also still out of the active rotation until it is recovered and
manually re-verified the same way.

## What Is Not Modern

The direct-stream `game-backuper` plan under
[`inventory/storage/backup-plans/game-library-copy1.nix`](/work/flake/inventory/storage/backup-plans/game-library-copy1.nix)
is a legacy raw-tape/LTO-4 path.

It is not the modern plan.

Do not treat the `game-backuper-game-library-copy1` workflow as the primary
game-library backup target when the goal is LTFS on the `L5` drives.

## Operator Shape

The modern plan is intentionally simple at the hardware layer:

1. Start the declarative workflow with `backupper start game_backup`.
2. Let `backupper` use both configured drives and load the assigned `L5` tapes.
3. Let `backupper` mount LTFS, index what is already present, and skip files
   that are already backed up on the loaded tape.
4. Let `backupper` stream the archive roots directly to tape without staging
   through a local cache.
5. Let the normal background service reconcile interrupted active writes and
   resume the current selected-tape rotation.
6. If one tape has LTFS consistency trouble, let `backupper` move that job to
   `needs_operator` and continue with the rest of the run where possible.
7. If a tape is removed from the active rotation, let `backupper` ignore its
   stale queued or operator-blocked write jobs so they do not poison future
   planning.
8. Let `backupper` emit an archive-coverage report for loose unzipped game
   files so non-represented content can be caught and reviewed. That report
   checks zip members by exact relative path plus size first, then falls back
   to basename plus size when needed.
9. Use the lower-level `mtx`, `mt1`, `mt2`, `ltfs-default`, and
   `ltfs-default-2` tools for inspection, recovery, or manual intervention.

## Read Next

- [`docs/tape-library/README.md`](/work/flake/docs/tape-library/README.md)
- [`docs/tape-library/backupper.md`](/work/flake/docs/tape-library/backupper.md)
- [`docs/tape-library/ltfs/README.md`](/work/flake/docs/tape-library/ltfs/README.md)
- [`docs/tape-library/hardware/README.md`](/work/flake/docs/tape-library/hardware/README.md)
- [`experiments/tapelib/docs/README.md`](/work/flake/experiments/tapelib/docs/README.md)
