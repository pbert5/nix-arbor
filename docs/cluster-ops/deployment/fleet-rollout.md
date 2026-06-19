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

Preview it first with:

```bash
nix run .#clusterctl -- deploy all --dry-run
```

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

- `t320-0` keeps some replicated ZFS backup datasets under `/big/backup/...`
  from its earlier TrueNAS layout. Those read-only parents can make plain
  `zfs mount -a` report child mountpoint-creation failures during activation,
  so the host override now marks the replicated `.../mypool/lxd` descendants
  `canmount=noauto` before `zfs-mount.service` runs.
- `t320-0` does not boot from LVM. Host-side LVM scanning is disabled there so
  read-only backup zvols like `/dev/zd*` do not trigger stale VG
  auto-activation attempts and leave `systemd` in `degraded`.
