# Tape Library Tooling

This folder tracks the extra tape workflows we are layering on top of the base
TL2000 + LTO drive setup.  The library is now attached to `t320-0`.

Checked upstream on April 20, 2026.

## Modern Plan

The modern tape backup plan for this repo is LTFS on the `L5` tapes attached to
`t320-0`.

Read this first:

- [Modern Tape Backup Plan](./modern-backup-plan.md)
- [Backupper](./backupper.md)

The old raw `game-backuper` LTO-4 direct-stream path is legacy context only.
It is not the modern tape backup plan.

## Local Packages

- `fossilsafe`
  Historical LTFS-focused archive workflow kept in-tree for reference.
- `stfs`
  Tar-oriented tape filesystem workflow for direct tape archives and older
  non-LTFS media such as LTO-4.
- `yatm`
  Dedicated LTFS tape browser and job UI.

## Local Notes

- [FossilSafe](./fossilsafe/README.md)
- [LTFS](./ltfs/README.md)
- [STFS](./stfs/README.md)
- [YATM](./yatm/README.md)

## Upstream Indexes

- [FossilSafe Upstream Docs](./fossilsafe/upstream.md)
- [LTFS Upstream Docs](./ltfs/upstream.md)
- [STFS Upstream Docs](./stfs/upstream.md)
- [YATM Upstream Docs](./yatm/upstream.md)

## Current Split

- The modern game-library target is the LTFS/LTO-5 workflow documented in
  [Modern Tape Backup Plan](./modern-backup-plan.md).
- The modern command surface for that workflow is `backupper`.
- The active plan is `game_backup`, defined in
  [`inventory/storage/backup-plans/game_backup.nix`](/work/flake/inventory/storage/backup-plans/game_backup.nix).
- The modern plan keeps the useful staged-planning ideas from the archived
  `tapelib` work, but runs them through the active `backupper` service instead
  of reviving the archived `tapelib` services.
- LTFS manager selection, when enabled for a host, lives in
  [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix) under
  `org.storage.tape.manager`.
- The FossilSafe fork remains under
  [`fruits/fossilsafe`](/work/flake/fruits/fossilsafe) for reference.
- YATM config is also inventory-driven now and is rendered to
  `/etc/yatm/config.yaml` when the tape-library dendrite is present.
- `t320-0` selects the tape-library dendrite, but does not attach FossilSafe or
  YATM.  The shared host substrate is the important active layer right now:
  `mtx`, `mt1`, `mt2`, `tape-default`, `tape-default-2`, `ltfs-default`, and
  `ltfs-default-2`.
- The abandoned tapelib implementation is archived under
  [`experiments/tapelib`](/work/flake/experiments/tapelib) and is not wired
  into the active system flake.
- The hardware-attached `L5` tapes used by the LTFS-era examples include
  `385182L5`, `430550L5`, and `383685L5`.
- The older raw `game-backuper` plan under
  [`inventory/storage/backup-plans`](/work/flake/inventory/storage/backup-plans)
  is still in-tree as legacy context, but it is not the modern LTFS target.
- Manual `mtx`/`ltfs` remains useful for emergency operation, but normal TL2000
  work is currently centered on the shared declarative hardware substrate plus
  the documented LTFS operator flow.
- Choose either `fossilsafe` or `yatm` per host, not both at once, so they do
  not contend for the same changer and drive state.
- Ports now come from [`inventory/ports.nix`](/work/flake/inventory/ports.nix)
  with explicit bind/host/CIDR metadata so local-only and Tailscale-only
  exposure is described in one place.
- Keep the base hardware helpers in
  [`docs/tape-library/hardware/README.md`](/work/flake/docs/tape-library/hardware/README.md) and
  [`docs/tape-library/hardware/coding/README.md`](/work/flake/docs/tape-library/hardware/coding/README.md).
