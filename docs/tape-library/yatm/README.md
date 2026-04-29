# YATM

Local package: `yatm`

Status: packaged and configured through Nix, but not the selected LTFS manager
for `desktoptoodle` right now.

Companion commands:

- `yatm`
- `yatm-httpd`
- `yatm-export-library`
- `yatm-lto-info`

## What We Added

- Repo-local package under
  [`dendrites/storage/dendrites/tape/_packages/yatm.nix`](/work/flake/dendrites/storage/dendrites/tape/_packages/yatm.nix)
- Wrapped around upstream release `v0.1.21`
- Declarative config rendered from host inventory to `/etc/yatm/config.yaml`

## Integration Notes

- Host-specific YATM settings now live in
  [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix) under
  `org.storage.tape.yatm`.
- The rendered config seeds listen ports from
  [`inventory/ports.nix`](/work/flake/inventory/ports.nix) and merges in
  any host-specific YATM settings from inventory.
- Upstream helper scripts are patched so captured LTFS indexes live in the user
  state directory instead of `/opt/yatm`.
- When YATM is the selected manager, the wrapper picks up
  `/etc/yatm/config.yaml` plus the configured `YATM_STATE_DIR` instead of
  first-run-seeding everything under XDG paths.
- Which host uses `yatm` vs `fossilsafe` now comes from
  [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix) via
  `org.storage.tape.manager`.
- YATM and FossilSafe both want direct control over the same changer and tape
  drive state, so each host should select one or the other, not both.
- This package expects LTFS-capable media. For the current HH5 drive, that
  means using `ltfs-open` and the `ltfs-default` SG-device path.

## Quick Start

```bash
yatm
```

If you need to change YATM behavior, edit the host inventory instead of editing
runtime config files by hand:

- `facts.storage.tape.devices`
- `org.storage.tape.yatm.settings.paths.source`
- `org.storage.tape.yatm.settings.paths.target`
- `org.storage.tape.yatm.stateDir`
