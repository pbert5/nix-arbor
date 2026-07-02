# Fleet Rollout

This guide is about deployment patterns after a host is enrolled.

## Pick The Tool For The Risk

Use `deploy-rs` when the change could break connectivity:

- SSH policy
- firewall policy
- network topology
- Ygg listener or peer changes

Use Colmena when the change is broad and you want fast fan-out:

- common package or service changes
- multiple-node trust propagation
- repeated routine rollout across a stable fleet

## Common Rollout Shapes

### One Host, Risky Change

```bash
nix run .#clusterctl -- deploy r640-0
```

Use for:

- first switch to Ygg transport
- root SSH changes
- strict peer-lockdown enablement

When this command is run from an operator-capable leader as a non-root user,
`clusterctl` re-runs itself under `sudo` for the actual deploy so the leader's
host-local root deploy key is available. Dry runs stay unprivileged.

### One Host, Routine Change

```bash
nix run .#colmena -- apply --on r640-0
```

Use for:

- non-networking updates
- quick iteration on a single host

### Several Named Hosts

```bash
nix run .#clusterctl -- deploy r640-0 desktoptoodle
```

Use for:

- updating a peer set together
- rolling out trust changes to a known subset

This is the normal multi-host path when you still want `deploy-rs` activation
semantics and target-resolution output for each host.

### Whole Fleet

```bash
nix run .#clusterctl -- deploy all
```

Use for:

- converging the whole exported fleet after shared module or inventory changes
- applying trust or identity changes cluster-wide from a leader

`clusterctl` compares each host's current `boot.json` and generated `fstab`
against the proposed NixOS closure before activation. Hosts with filesystem,
kernel, initrd, kernel-parameter, or bootloader metadata changes are removed
from the Colmena fan-out and deployed sequentially through deploy-rs. Hosts
whose current state cannot be verified are treated as boot-risky too.

The protected deploy-rs routes run first. If one fails, routine Colmena
activation does not begin for the remaining hosts.

Preview it first with:

```bash
nix run .#clusterctl -- deploy all --dry-run
```

The preview builds and inspects boot state, prints the selected route for every
host, and runs Colmena `dry-activate` only for hosts classified as unchanged.
It never invokes deploy-rs activation.

### Enrolled Host Plus Its Peers

Preferred sequence:

1. deploy the newly enrolled host
2. deploy the peers that should trust it
3. confirm the deploy surface now points where expected

This is the safe shape for trust propagation because it keeps the inventory
transition and the runtime transition legible.

## Pre-Flight Checks

Before a rollout, especially a network-sensitive one, check:

- `nix eval '.#deploy.nodes.<host>' --json`
- `nix run .#clusterctl -- deploy <host> --dry-run`
- root SSH from a trusted leader still works
- the enrolled host has the expected Ygg public metadata

## Post-Flight Checks

After a rollout, check:

- `deploy-rs` or Colmena reported activation success
- the deploy surface still resolves to the expected transport
- the relevant peers can still reach one another

## Host Notes

- `r640-0` boots from plain ext4 and uses ZFS for managed storage. Host-side
  LVM scanning is disabled so retired Proxmox media and LVM signatures inside
  backup zvols do not trigger failed auto-activation units.
- `t320-0` boots systemd-boot through the removable-media fallback path
  `EFI/BOOT/BOOTX64.EFI`. Its firmware NVRAM contains legacy boot entries and
  has no room for another variable, so the host deliberately sets
  `boot.loader.efi.canTouchEfiVariables = false`.
- `t320-0` keeps some replicated ZFS backup datasets under `/big/backup/...`
  from its earlier TrueNAS layout. Those read-only parents can make plain
  `zfs mount -a` report child mountpoint-creation failures during activation,
  so the host override now marks the replicated `.../mypool/lxd` descendants
  `canmount=noauto` before `zfs-mount.service` runs.
- `t320-0` does not boot from LVM. Host-side LVM scanning is disabled there so
  read-only backup zvols like `/dev/zd*` do not trigger stale VG
  auto-activation attempts and leave `systemd` in `degraded`.
