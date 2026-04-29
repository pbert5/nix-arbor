# Changes

This file summarizes the current dendritic refactor as it exists in the code.

## Implemented

- The active flake root is tiny and routes into `flake-parts`.
- `modules/flake-parts/` now owns root glue instead of the old hand-wired
  module tree.
- Registry discovery now comes from:
  - `dendrites/`
  - `fruits/`
  - `homes/`
  - `hosts/`
- `inventory/hosts.nix` now uses the newer host vocabulary:
  - `facts`
  - `org.*`
  - `overrides`
  - `fruits`
- `lib/inventory.nix` normalizes older fields like `hostModules`, `zfsPool`,
  and `tapeLibrary` into the newer shape.
- Dendrites and fruits now carry required `meta.nix`.
- Dendrite discovery now follows explicit nested `dendrites/.../dendrites/...`
  chains instead of stopping after a single child level.
- Validation now checks both inventory correctness and resolved host
  composition.
- The repo already enforces a no-`default.nix` rule through
  `checks/no-default-nix.nix`.
- `inventory/networks.nix` now defines a private Yggdrasil topology and shared
  firewall defaults.
- Hosts now opt into named networks through `inventory/hosts.nix` `networks = [ ... ]`,
  and each network definition declares its backing dendrite.
- `network/yggdrasil-private` now builds host Yggdrasil settings from
  inventory, including peer lists and optional overlay aliases.
- `network/tailscale` is now a separate selectable dendrite instead of a base
  service enabled everywhere.
- Hosts now select private Yggdrasil and selective Tailscale through explicit
  network membership instead of role-driven dendrite attachment.
- The private Yggdrasil firewall model now enforces explicit overlay allowlists
  and rejects unsafe `trustedInterfaces` shortcuts.
- The flake now exposes generated deployment surfaces for Colmena and
  deploy-rs.
- Checks now cover the private overlay model, a Yggdrasil smoke test, generated
  deployment targets, and deploy-rs schema/activation validation.

## Concrete Current Examples

- `r640-0` explicitly selects `storage/zfs` and provides
  `facts.storage.zfs.poolName` and `facts.storage.zfs.rootMountPoint`.
- `desktoptoodle` explicitly selects `system/workstation/gaming` for Steam,
  selects `storage/tape`, attaches the `fossilsafe` fruit, and stores tape
  device paths under `facts.storage.tape.devices`.
- `desktoptoodle` also layers host-specific desktop tools through
  `hosts/desktoptoodle/user1-desktop.nix`, including OBS Studio plus PipeWire
  routing controls for local capture and microphone troubleshooting, and its
  OBS package is now built with CUDA/NVENC support for the NVIDIA desktop.
- `fossilsafe` is now modeled as a fruit rather than just an internal module.
- `dev-machine`, `r640-0`, and `desktoptoodle` are exported hosts that now get
  a private Yggdrasil mesh plus selective Tailscale bridging via explicit
  network membership.
- `compute-worker` gets explicit private Yggdrasil network membership but remains
  non-exported for deployment surfaces.
- `flake.colmenaHive` and `flake.deploy` are generated from inventory instead
  of being hand-written host maps.

## Not Yet Fully Realized

- The root flake does not yet expose a hand-written composition library directly
  from `flake.nix`; it still routes through `flake-parts`.
- Some older host override files still carry work that could move further into
  dendrites over time.
- The private-cluster plan is still only partially realized: there is not yet a
  repo-managed public Yggdrasil sidecar, private binary cache service over Ygg,
  or Radicle integration in the primary flake.

## Why The Docs Changed

Some earlier docs still described the older `modules/dendrites`,
`modules/home`, and `modules/hosts` architecture as if it were current. The
docs now match the code that actually assembles the flake today.

For the overlay and deployment additions specifically, see
[`docs/private-overlay-and-deployments.md`](/work/flake/docs/private-overlay-and-deployments.md).
