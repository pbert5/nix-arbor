# Tape Library Tooling

This folder tracks the extra tape workflows we are layering on top of the base
TL2000 + HH5 setup on `desktoptoodle`.

Checked upstream on April 20, 2026.

## Local Packages

- `tapelib`
  Catalog-first tape-library overlay scaffold with a persistent SQLite
  catalog/job journal, aimed at a FUSE + queued-job workflow.
- `fossilsafe`
  Historical LTFS-focused archive workflow kept in-tree for reference, but no
  longer selected as the active manager on `desktoptoodle`.
- `stfs`
  Tar-oriented tape filesystem workflow for direct tape archives and older
  non-LTFS media such as LTO-4.
- `yatm`
  Dedicated LTFS tape browser and job UI.

## Local Notes

- [FossilSafe](./fossilsafe/README.md)
- [LTFS](./ltfs/README.md)
- [STFS](./stfs/README.md)
- [Tapelib](./tapelib/README.md)
- [YATM](./yatm/README.md)

## Upstream Indexes

- [FossilSafe Upstream Docs](./fossilsafe/upstream.md)
- [LTFS Upstream Docs](./ltfs/upstream.md)
- [STFS Upstream Docs](./stfs/upstream.md)
- [YATM Upstream Docs](./yatm/upstream.md)

## Current Split

- LTFS manager selection is host-specific and lives in
  [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix) under
  `org.storage.tape.manager`.
- The tapelib successor scaffold now lives under
  [`fruits/tapelib`](/work/flake/fruits/tapelib) and currently focuses on
  service/module shape, persistent catalog/job-journal storage, a read-only
  `/mnt/tapelib` FUSE browser surface using `browse`, `readable`, `write`,
  `thumbnails`, `jobs`, and `system`, read-only TL2000 inventory, journaled
  LTO-5 LTFS hardware commands, additive inventory manifests, and game-archive
  planning.
- The FossilSafe fork remains under
  [`fruits/fossilsafe`](/work/flake/fruits/fossilsafe) for reference, but
  new TL2000 service work should target tapelib.
- YATM config is also inventory-driven now and is rendered to
  `/etc/yatm/config.yaml` when the tape-library dendrite is present.
- `desktoptoodle` currently selects `org.storage.tape.manager = "tapelib"` and
  attaches the `tapelib` fruit.
- L4 media is ignored by tapelib for now. Use `stfs` plus `tape-default` later
  if direct LTO-4 tar workflows become necessary.
- Manual `mtx`/`ltfs` remains useful for emergency operation, but normal TL2000
  work should go through tapelib so the SQLite catalog, locks, and job journal
  stay coherent. After manual movement, run `tapelib inventory` and
  `tapelib reconcile-hardware`.
- Choose either `fossilsafe` or `yatm` per host, not both at once, so they do
  not contend for the same changer and drive state.
- Ports now come from [`inventory/ports.nix`](/work/flake/inventory/ports.nix)
  with explicit bind/host/CIDR metadata so local-only and Tailscale-only
  exposure is described in one place.
- Keep the base hardware helpers in
  [`docs/tape-library.md`](/work/flake/docs/tape-library.md) and
  [`docs/tape-library-coding-guide.md`](/work/flake/docs/tape-library-coding-guide.md).
