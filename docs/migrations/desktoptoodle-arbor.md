# desktoptoodle Arbor migration

desktoptoodle uses the shared TilingDesktop Niri and text tuigreet modules.
Host-specific NVIDIA, dual-monitor, Blue USB microphone, and gaming settings
live in `config/machines/desktoptoodle/`; reusable desktop behavior remains in
the component submodule.

Build and inspect the host with:

```sh
nix build .#nixosConfigurations.desktoptoodle.config.system.build.toplevel
sudo nixos-rebuild test --flake .#desktoptoodle
```

The BitLocker game disk integration is enabled for the confirmed live UUID
`657ff291-de57-40c0-80d9-9362895587e8`, while recovery files remain operator-
local under `/home/ash/.config/bitlocker-recovery/`. The unit is wanted by
`multi-user.target`, not required by local-fs, so an absent disk does not block
boot. The module never formats, repairs, or resizes the volume.

Ash and root SSH remain key-only. Root SSH is an accepted temporary recovery
path and is limited to the existing `r640EvolverDeployer` public key grant.
Ash's local password must be supplied through a pre-provisioned secret-backed
runtime path before relying on tuigreet password authentication; no password
or hash is stored in this repository.

Rollback is available through the previous systemd-boot generation, or by
using `sudo nixos-rebuild test` (which does not make the tested generation the
persistent boot default).
