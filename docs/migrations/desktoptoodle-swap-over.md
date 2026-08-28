# desktoptoodle swap-over guide

This guide is a preservation index for the legacy Flake Devbox host. The
current Nix Arbor profile is incremental. Nothing listed here is permission to
delete the legacy checkout, its generations, or its runtime state. Keep the
exact source paths below available for comparison, rollback, and fast
capability restoration.

## Current ownership

The machine-specific file `config/machines/desktoptoodle/configuration.nix`
owns the desktop machine's import of `config/users`. Do not also add that
module to the shared `desktop` profile: the unique `ash.shell` option would be
defined twice and evaluation would fail.

The external account interface is path-only. The operator must materialize
`accounts.ash.password-hash` to `/run/secrets/ash-password` before activating
the desktop profile. The private recovery repository is optional operator data,
never a Nix input.

## Restored public capabilities

`config/machines/desktoptoodle/configuration.nix` carries the evidenced live
host settings for NetworkManager, Tailscale client mode, Docker development,
the 6.18 kernel line, camera module, NVIDIA modesetting/package selection,
dual-monitor Kanshi session, pointer setting, Blue USB microphone profile, and
camera/audio/hardware/development utilities. Tailscale enrollment and all
credentials remain operator/runtime state.

## Legacy capability index

| Capability | Exact legacy authority or live source | Nix Arbor status | Swap-over action or blocker |
| --- | --- | --- | --- |
| Account UID/GID/groups/shell | `/home/ash/flake/config/users.json`, `state/identity-services` | Imported through `config/users` | Validate UID 1000 and groups before test activation. |
| SSH server/public login keys | `/home/ash/flake/config/external-incoming-access.json`, live `authorized_keys` | Public keys retained; private keys external | Compare fingerprints and materialize only required client keys. |
| SSH client identities | `/home/ash/flake/config/external-outgoing-access.json`, `state/identity-services/leader-user-ssh.nix` | Path metadata only | Add an allowlisted recovery entry and materialize to the declared path. |
| GitHub/GitLab/Docker auth | Live `gh`, `glab`, Docker configuration | Runtime/operator state | Re-provision through recovery/provider; never add tokens to Nix. |
| NetworkManager/Wi-Fi/VPN | `/home/ash/flake/src/dendrites/network`, live `/etc/NetworkManager/system-connections` | NetworkManager enabled | Preserve profiles root-only and validate connectivity. |
| Tailscale | Legacy `network/tailscale`, live daemon state | Client enabled; enrollment external | Confirm tailnet identity and routes. |
| Yggdrasil overlays | Legacy `network/yggdrasil-private`, `state/identity-services/yggdrasil.nix` | BLOCKED | Inventory and materialize private host identity before enabling. |
| NVIDIA/kernel/camera/audio/session | `/home/ash/flake/src/hosts/desktoptoodle/desktoptoodle.nix`, legacy hardware module | Public capability restored | Validate display, PipeWire, camera, and dual-monitor session. |
| BitLocker mounts | Legacy `storage/bitlocker`, live mount inventory | BLOCKED | Reconcile device identifiers and key material; never guess devices. |
| SeaweedFS `/hot` | Legacy `storage/seaweedfs-hot`, live service state | BLOCKED | Confirm workload ownership and credentials before restoring. |
| Docker workloads | Live Meta WebUI/eVOLVER containers and legacy workload definitions | Docker enabled; workloads not selected | Record each workload and secret scope before re-declaring it. |
| Git-annex/Radicle/IPFS cluster | Legacy storage/network dendrites and identity ledgers | BLOCKED | Each service needs a current consumer and recovery entry. |
| Boot rollback | Live generations and systemd-boot | Retained | Keep prior generations; never remove them during migration. |

## Safe swap-over sequence

1. Record `/run/current-system`, boot entries, mounts, interfaces, and service
   health on the live host.
2. Materialize only credentials whose catalog consumer is `desktoptoodle`; verify
   ownership, mode, fingerprint, and digest.
3. Add one capability group at a time, keeping `/home/ash/flake` untouched and
   recording the acceptance command here.
4. Build Nix Arbor and inspect the closure; then use `nixos-rebuild test`.
5. Validate SSH, account identity, NetworkManager, Tailscale/Yggdrasil,
   display/session, PipeWire, camera, mounts, Docker workloads, and tools.
6. Switch only after required capabilities are green. Retain prior generations
   and the legacy configuration for rollback.

If a capability is not restored, classify it as `MISSING` or `BLOCKED`; do not
call it retired merely because it is absent from the current profile.
