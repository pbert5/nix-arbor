# Backupper

`backupper` is the modern command surface for game-library tape backups on this
repo.

It is the thing to use on `t320-0`.

## Modern Defaults

- Plan name: `game_backup`
- Plan file:
  [`inventory/storage/backup-plans/game_backup.nix`](/work/flake/inventory/storage/backup-plans/game_backup.nix)
- Service name: `backupper-game_backup.service`
- Control command: `backupper`
- Tape format: LTFS on `L5`
- Drives used: both configured `LTO-5` drives
- Data path: source disk directly to LTFS tape
- Payload intent: archive files from `_source-archives` and `incoming`
- Loose `roms` trees: coverage-audited, not written as primary payload

This modern path does not stage archive payloads into a local cache first.

It reads directly from `/big/GameLibrary/...` and writes directly onto LTFS.

The current active `L5` rotation starts with `383685L5`, `384933L5`, and
`384333L5`. `430550L5` and `385182L5` are temporarily out of rotation pending
deeper recovery and re-verification.

## Commands

Run the modern game backup:

```bash
backupper start game_backup
```

Run every declarative backupper plan available on the machine:

```bash
backupper start
```

Explicitly retry failed or `needs_operator` write jobs for a plan:

```bash
backupper resume game_backup
```

Inspect status:

```bash
backupper status game_backup
journalctl -u backupper-game_backup.service -f
```

List plans:

```bash
backupper list
```

## Behavior

- The planner assigns tapes to both drives so both `LTO-5` drives can work in
  the same run.
- The active `game_backup` plan writes the archive roots, not the loose
  unzipped `roms` trees.
- The background service reconciles interrupted active writes on startup and
  resumes the current selected-tape rotation by default.
- Jobs for tapes that were removed from the active rotation do not block new
  planning or resumed writes.
- Use `backupper resume <plan>` when you want an explicit transient retry run
  outside the normal service unit.
- Before queueing writes, `backupper` generates
  `/var/lib/backupper/<plan>/status/archive-coverage.json` and checks whether
  loose files under `roms` are represented inside the configured zip archive
  roots.
- That coverage audit prefers exact relative-path-plus-size matches and then
  falls back to basename-plus-size matches when the zip layout differs from the
  loose tree layout.
- Before a write, the runner refreshes changer inventory, loads the correct
  tape into the assigned drive, mounts LTFS read-write, and indexes the loaded
  tape.
- If LTFS mount or tape prep fails for one cartridge, that write job is moved
  to `needs_operator` so the rest of the run can continue.
- If the loaded LTFS tape already contains a file with matching content, that
  file is not written again.
- If a tape already has part of the planned data, the missing remainder is
  written and the existing files are skipped.
- The old raw `game-backuper` `LTO-4` path is legacy context only.

## Current Truth

When the goal is the current game-library tape workflow, use `backupper` and
the `game_backup` plan.
