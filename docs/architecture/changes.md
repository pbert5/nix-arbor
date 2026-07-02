# Changes

This file summarizes the current dendritic refactor as it exists in the code.

## Implemented

- The primary flake, its public-export overlay, and the standalone FossilSafe
  fruit now track NixOS 26.05. Home Manager tracks its matching `release-26.05`
  branch; existing system and home state versions remain at 25.11 to preserve
  upgrade compatibility.
- Home Manager SSH configuration uses the 26.05 `programs.ssh.settings`
  interface, and ZFS hosts explicitly preserve the prior root-pool import
  behavior rather than inheriting a future default change. The live installer
  disables forced root-pool import because it has no root ZFS pool.
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
  network membership instead of indirect dendrite attachment.
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
  `system/workstation/remote-desktop` for Sunshine/Moonlight access, plus
  SeaweedFS and Radicle storage-fabric branches. It does not currently select
  the tape-library dendrite or a tape fruit.
- `desktoptoodle` now selects `desktop/hyprland` instead of `desktop/gnome`.
  The dendrite owns the SDDM-launched UWSM Hyprland session, XDG portals,
  PipeWire and WirePlumber, and a shared Home Manager configuration for Kitty,
  Rofi, Waybar, Awww, SwayNotificationCenter, Hypridle, Hyprlock, Dolphin, and
  Hyprpolkitagent.
- `desktop/hyprland-minimal` is available as a smaller recovery branch while
  the fuller Hyprland branch is being stabilized. The minimal branch keeps only
  a text greetd login, UWSM-launched Hyprland, basic graphics/input/audio,
  Kitty, Rofi, and starter key bindings.
- `desktoptoodle` also layers host-specific desktop tools through
  `hosts/desktoptoodle/user1-desktop.nix`, including OBS Studio, and
  CrossPipe PipeWire routing controls for local capture and microphone
  troubleshooting,
  VIA keyboard configuration software, and its OBS package is now built with
  CUDA/NVENC support for the NVIDIA desktop.
- `desktoptoodle` selects `network/warpinator` for native LAN file transfer;
  that dendrite installs Warpinator and owns its narrowly scoped firewall
  ports.
- `system/workstation` now enables QMK keyboard support and ships VIA udev
  rules for interactive workstation hosts, and now pins Docker to the
  maintained `docker_29` package line so deployment evaluation does not fail on
  the retired `docker_28` default.
- `desktoptoodle` temporarily forces `pkgs.linuxPackages_latest` and blocks
  `algif_aead` to mitigate CopyFail while that workaround remains necessary.
- `desktoptoodle:eno1` and `t320-0:eno2` form a private gigabit point-to-point
  link on `10.200.0.0/30`. The `network/direct-link` dendrite installs static,
  gateway-free NetworkManager profiles and `<peer>-direct` SSH aliases.
- `desktoptoodle` enables Flatpak and reconciles the per-user Flathub
  `org.jdownloader.JDownloader` application at login. JDownloader is absent
  from the pinned Nixpkgs package sets, so this is an explicit packaging
  exception rather than an unmanaged installer.
- `fossilsafe` is now modeled as a fruit rather than just an internal module.
- `r640-0`, `desktoptoodle`, and `t320-0` are the active exported hosts with
  private Yggdrasil membership. Retired `dev-machine` and placeholder
  `compute-worker` records now live under `inventory/deprecated/`.
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
[`docs/repo-ops/private-overlay/README.md`](/work/flake/docs/repo-ops/private-overlay/README.md).
