# LTFS

This is part of the modern tape backup plan for this repo.

Read [Modern Tape Backup Plan](../modern-backup-plan.md) first if you are
confirming the current intended workflow.

The modern game-library LTFS workflow is driven by
[`backupper`](../backupper.md), not by the older raw `game-backuper` path.

In the active `game_backup` plan, LTFS payloads come from the archive roots.
Loose unzipped `roms` files are checked for coverage against the zip archive
set and reported separately.

Local package: `ltfs-open`

Companion helpers:

- `ltfs-default`
- `mkltfs`
- `ltfs`
- `ltfsck`

## What We Added

- Repo-local package under
  [`fruits/fossilsafe/nix/ltfs-open.nix`](/work/flake/fruits/fossilsafe/nix/ltfs-open.nix)
- Default LTFS device helper under
  [`dendrites/storage/dendrites/tape/_packages/ltfs-default.nix`](/work/flake/dendrites/storage/dendrites/tape/_packages/ltfs-default.nix)
- IBM-compatible open LTFS build based on upstream `LinearTapeFileSystem/ltfs`

## Integration Notes

- On this host, LTFS must use the drive's generic SCSI node, not the
  non-rewinding tape node used by `mt` and `tar`.
- `ltfs-default` resolves the current default tape drive to the matching
  `/dev/sg*` path.
- `ltfs-default-2` resolves the second configured tape drive to its matching
  `/dev/sg*` path.
- The tested Linux path for the HH5 drive here is the open LTFS build, not the
  HPE build that rejected `ULT3580-HH5`.
- For the current TL2000 + HH5 setup:
  - `tape-default` resolves to the non-rewinding stream device.
  - `tape-default-2` resolves the second configured non-rewinding stream
    device.
  - `ltfs-default` resolves to the LTFS device for `mkltfs`, `ltfs`, and
    `ltfsck`.
  - `ltfs-default-2` resolves the LTFS SG device for the second configured
    drive.

## Quick Start

```bash
backupper start game_backup
backupper status game_backup
ltfs -o device_list
ltfs-default
ltfs-default-2
mkltfs -d "$(ltfs-default)" -n LTFS001
mkdir -p ~/mnt/ltfs
ltfs ~/mnt/ltfs -o devname="$(ltfs-default)"
umount ~/mnt/ltfs
```

## Index Sync Behavior

- Verified on `t320-0` on May 19, 2026 with the live `ltfs --help`
  output from `/run/current-system/sw/bin/ltfs`.
- The current default mount behavior is `-o sync_type=time@5`.
- That means LTFS attempts to write the index to tape every 5 minutes while
  writes are happening.
- A clean unmount also writes the current metadata and closes the tape cleanly.
- LTFS also supports `-o sync_type=close` and `-o sync_type=unmount` if you
  want a different checkpoint policy.

## Switching Modes

- LTFS and raw tape workflows are mutually exclusive on the same loaded tape.
- Before switching from LTFS back to `mt`, `tar`, `stfs`, or any other raw tape
  tool, run `umount <mountpoint>` and wait until the `ltfs` process exits.
- If FossilSafe or YATM has the drive loaded, stop that manager before mounting
  LTFS by hand so the changer and mount state stay coherent.
- Before switching from raw tape work to LTFS, make sure no `mt`, `tar`, or
  manager workflow is still touching the drive, then mount LTFS by using
  `ltfs-default`.
- On this host, `tape-default` is for raw tape streams and `ltfs-default` is
  for LTFS only.

## Recovery Notes

- Use `ltfsck -d "$(ltfs-default)"` when you need LTFS metadata repair or
  validation.
- `backupper` indexes a loaded LTFS tape before writing, so files already
  present on that tape are skipped instead of rewritten.
- Do not run `mt`, `tar`, or other raw tape commands against the same drive
  while LTFS has the tape mounted.
- Use
  [`docs/tape-library/hardware/coding/README.md`](/work/flake/docs/tape-library/hardware/coding/README.md)
  for explicit device mappings and longer command forms.
