# `storage/tape`

Tape-library support branch.

## Purpose

Provides the shared OS-level setup for LTFS-backed tape workflows, including
tooling, environment wiring, and manager selection.

## Main Effects

- enables required kernel modules such as `sg` and `st`
- installs LTFS and tape tooling
- installs `mt`, `mt1`, and `mt2` helpers for the default, first, and second
  detected non-rewinding drives
- generates YATM config only when `org.storage.tape.manager = "yatm"`
- renders `game-backuper` plan YAML for plans in `site.storage.backupPlans`
  that target the current host
- installs `game-backuper-<plan-name>` wrapper commands for manual operation
- adds matching `game-backuper-<plan-name>.service` oneshots for supervised
  live writes and journal-based monitoring
- exports tape-related arguments through `_module.args.storageTape`

## Inventory Inputs

- `facts.storage.tape.devices`
- `org.storage.tape.manager`
- `org.storage.tape.fossilsafe.*`
- `org.storage.tape.yatm.*`
- `site.storage.backupPlans`

If `org.storage.tape.manager` is omitted, this branch still provides the shared
tape substrate and tooling, but it does not pull in a manager-specific package
or enable a fruit-backed service. It also skips rendering manager-specific
config such as `/etc/yatm/config.yaml`.

## Requirements

- requires `storage`
- intended for `workstation` hosts

## Notes

This branch is the shared storage/tape substrate. Fruit-level behavior lives in
the fruit layer and only activates when a host explicitly opts into a concrete
manager such as `org.storage.tape.manager = "fossilsafe";` or
`org.storage.tape.manager = "yatm";`.

`mt` continues to default to the first detected non-rewinding tape drive.
When `facts.storage.tape.devices.drives` is set, these helpers use that
declarative drive order first. `mt1` and `mt2` provide explicit first-drive and
second-drive wrappers; `mt2` will exit with a clear error if the configured
drive list does not include a second entry. `tape-default-2` and
`ltfs-default-2` provide the matching second-drive helpers for raw tape and
LTFS work.

The modern game-library plan is the LTFS/LTO-5 workflow documented in
[`docs/tape-library/modern-backup-plan.md`](/work/flake/docs/tape-library/modern-backup-plan.md).
The modern command surface for that workflow is
[`backupper`](../../../../docs/tape-library/backupper.md), using the
`game_backup` plan.
The older raw `game-backuper` LTO-4 path remains in-tree as legacy context, but
it is not the modern plan.
