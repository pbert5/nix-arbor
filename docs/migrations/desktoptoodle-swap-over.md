# desktoptoodle swap-over guide

This guide is a preservation index for the legacy Flake Devbox configuration.
The current Nix Arbor profile is deliberately incremental. Nothing listed here
is permission to delete the legacy checkout, its generations, or its runtime
state. Use this guide to restore a capability quickly if an acceptance check
shows that the reduced profile is insufficient.

## Current ownership

The machine-specific file `config/machines/desktoptoodle/configuration.nix`
owns the desktop machine's import of `config/users`. Do not also add that
module to the shared `desktop` profile in `config/default.nix`: the `ash.shell`
option is unique and duplicate imports fail evaluation.

The external account interface is path-only. The operator must materialize
`accounts.ash.password-hash` to `/run/secrets/ash-password` before activating
the desktop profile. The private recovery repository is an optional operator
data source, never a Nix input.

## Legacy capability index

| Capability | Legacy authority to preserve | Current Arbor status | Swap-over action |
| --- | --- | --- | --- |
| Account UID/GID/groups/shell | `/home/ash/flake/config/users.json`, `state/identity-services` | Imported through `config/users` | Keep the import in the machine file; validate UID 1000 and groups before test activation. |
| SSH server and public login keys | `/home/ash/flake/config/external-incoming-access.json` and live `authorized_keys` | Public keys retained; private keys external | Compare fingerprints, then materialize only required client keys. |
| SSH client identities | `/home/ash/flake/config/external-outgoing-access.json`, `state/identity-services/leader-user-ssh.nix` | Path metadata only | Add an allowlisted recovery entry and materialize to the declared path. |
| GitHub/GitLab/Docker auth | Live `gh`, `glab`, Docker configuration | Runtime/operator state | Re-provision through the recovery store or provider; never add tokens to Nix. |
| NetworkManager/Wi-Fi/VPN | Live `/etc/NetworkManager/system-connections` | NetworkManager enabled | Preserve profiles with root-only extraction and test connectivity before switch. |
| Tailscale | Legacy `network/tailscale`, live daemon state | Client enabled; enrollment external | Confirm tailnet identity and routes; do not replace state casually. |
| Yggdrasil overlays | Legacy `network/yggdrasil-private`, live identity state | Not yet enabled for desktop | Restore the provider and identity only after endpoint/identity acceptance. |
| NVIDIA/kernel/camera/audio | `/home/ash/flake/src/hosts/desktoptoodle/desktoptoodle.nix` | Not fully ported | Port hardware-specific options as a separate reviewed change; test display, PipeWire, and camera. |
| BitLocker mounts | Legacy `storage/bitlocker` and live mount inventory | Not represented | Reconcile device identifiers and key material before enabling mounts; never guess devices. |
| SeaweedFS `/hot` | Legacy `storage/seaweedfs-hot` and live service state | Not represented | Restore only after confirming workload ownership and credentials. |
| Docker workloads | Live Meta WebUI/eVOLVER containers and legacy workload definitions | Docker enabled, workloads not selected | Record each workload and its secret scope before re-declaring it. |
| Git-annex/Radicle/IPFS cluster | Legacy `storage/git-annex`, `network/radicle`, cluster identity modules | Not represented | Treat as missing until each service has a current consumer and recovery entry. |
| Boot rollback | Legacy system generations and systemd-boot | systemd-boot retained | Keep prior generations; do not remove generations during migration. |

## Swap-over sequence

1. Record `/run/current-system`, boot entries, mounts, network interfaces, and
   service health on the live host.
2. Materialize only credentials whose catalog consumer is `desktoptoodle` and
   verify ownership, mode, fingerprint, and digest.
3. Add one capability group at a time, keeping the legacy Flake Devbox source
   untouched and recording the corresponding acceptance command here.
4. Build Nix Arbor and inspect the closure; then use `nixos-rebuild test`.
5. Validate SSH, account identity, NetworkManager, Tailscale/Yggdrasil,
   desktop/session, mounts, Docker workloads, and development tools.
6. Switch only after all required capabilities are green. Retain the prior
   generation and keep the legacy configuration available for rollback.

If a capability is not yet restored, classify it as `MISSING` or `BLOCKED` in
the migration matrix; do not label it retired merely because it is absent from
the current profile.
