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
- generates YATM config when needed
- exports tape-related arguments through `_module.args.storageTape`

## Inventory Inputs

- `facts.storage.tape.devices`
- `org.storage.tape.manager`
- `org.storage.tape.fossilsafe.*`
- `org.storage.tape.tapelib.*`
- `org.storage.tape.yatm.*`

If `org.storage.tape.manager` is omitted, this branch still provides the shared
tape substrate and tooling, but it does not pull in a manager-specific package
or enable a fruit-backed service.

## Requirements

- requires `storage`
- intended for `workstation` hosts

## Notes

This branch is the shared storage/tape substrate. Fruit-level behavior lives in
the fruit layer and only activates when a host explicitly opts into a concrete
manager such as `org.storage.tape.manager = "tapelib";`. FossilSafe remains
in-tree for reference, but the active TL2000 service path is tapelib.

`mt` continues to default to the first detected non-rewinding tape drive.
When `facts.storage.tape.devices.drives` is set, these helpers use that
declarative drive order first. `mt1` and `mt2` provide explicit first-drive and
second-drive wrappers; `mt2` will exit with a clear error if the configured
drive list does not include a second entry.
