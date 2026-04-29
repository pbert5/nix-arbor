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
nix run .#deploy-rs -- .#r640-0
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
nix run .#colmena -- apply --on r640-0,desktoptoodle
```

Use for:

- updating a peer set together
- rolling out trust changes to a known subset

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
- root SSH from a trusted leader still works
- the enrolled host has the expected Ygg public metadata

## Post-Flight Checks

After a rollout, check:

- `deploy-rs` or Colmena reported activation success
- the deploy surface still resolves to the expected transport
- the relevant peers can still reach one another
