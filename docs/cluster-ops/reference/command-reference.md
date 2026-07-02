# Command Reference

This page explains the commands we have been using and what each one actually
means.

For the shortest operator entry point, start with
[`clusterctl-quick-reference.md`](/work/flake/docs/cluster-ops/reference/clusterctl-quick-reference.md).

## Raw SSH Check

```bash
ssh -i /home/example/.ssh/deploy_rsa root@r640-0 'hostname && whoami'
```

Use this to verify that a bootstrap or leader deployer key can reach the target
as `root`.

What it proves:

- root SSH access works
- the host is reachable over the current management path
- the key in use is accepted by the target

Expected output shape:

- host name, such as `r640-0`
- user name, such as `root`

## Validate Bootstrap State

```bash
nix run .#bootstrap-validate
nix run .#nbootstrap -- validate
```

Use this before bootstrap and before deployment rollouts from a leader.

## Build The Live Installer

```bash
nix run .#live-installer
```

Use this when you want the dedicated bootstrap USB image that already trusts
the repo's leader deployer keys for `root` SSH.

Expected output shape:

- a `Build output:` path
- an `Image file:` path ending in `.iso`

## Write The Live Installer To USB

```bash
nix run .#live-installer-usb -- --device /dev/sdX
```

Use this after confirming the correct USB block device.

Expected output shape:

- `dd` progress
- a final `Wrote ... to /dev/sdX` line

## Ygg Identity Dry Run

```bash
nix run .#yggdrasil-bootstrap -- --host r640-0 --target 100.64.0.10 --identity-file /home/example/.ssh/deploy_rsa --dry-run
```

This connects to the target, ensures the Ygg key file exists, reads the public
key and derived Ygg address, and prints them without rewriting inventory.

Use it when:

- you want to verify SSH/bootstrap reachability
- you want to see what identity the host will publish
- you are debugging before making repo changes

## Bootstrap Host Dry Run

```bash
nix run .#bootstrap-host -- --host r640-0 --identity-file /home/example/.ssh/deploy_rsa --dry-run
```

This is the same bootstrap tool under a more operator-oriented name.

What is special here:

- it can omit `--target` if `inventory/host-bootstrap.nix` already has a
  `targetHost`
- it prints both the resolved bootstrap connection metadata and the discovered
  Ygg identity

For `r640-0`, the dry run currently resolves:

- bootstrap target: `100.64.0.10`
- ssh user: `root`

## Guided Bootstrap Host Dry Run

```bash
nix run .#nbootstrap -- host bootstrap --host r640-0 --identity-file /home/example/.ssh/deploy_rsa --dry-run
```

This is the higher-level operator path.

What is special here:

- it resolves inventory bootstrap metadata first
- it runs the raw SSH `hostname && whoami` check before enrollment
- it then hands off to the same lower-level Ygg enrollment logic

## Real Bootstrap Enrollment

```bash
nix run .#bootstrap-host -- --host r640-0 --identity-file /home/example/.ssh/deploy_rsa --deployment-transport privateYggdrasil
```

This updates:

- [`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
- [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)

It does not automatically force peer firewall lockdown.

## One-Shot Bootstrap With First Deploy

```bash
nix run .#nbootstrap -- \
  host bootstrap \
  --host r640-0 \
  --identity-file /home/example/.ssh/deploy_rsa \
  --deploy-tool deploy-rs
```

Use this when you want the repo to:

1. verify raw SSH reachability
2. enroll the host identity
3. immediately do the first deployment

## Show The Generated deploy-rs Target

```bash
nix eval '.#deploy.nodes.r640-0' --json
```

Use this to inspect what deploy-rs thinks the host should be called and how it
will connect.

This is the easiest way to confirm that a host has switched from bootstrap IP
transport to Ygg transport.

## Run The Pinned Deployment Tools

```bash
nix run .#deploy-rs -- .#r640-0
nix run .#deploy-rs -- .#desktoptoodle
nix run .#colmena -- apply --on r640-0
```

These use the flake-pinned tool versions instead of whatever happens to be in
your shell environment.

## Render Network Topology Diagrams

```bash
nix build .#topology.x86_64-linux.config.output -o ./topology-result
```

Use this to get a current SVG picture of the fleet instead of cross-referencing
`inventory/hosts.nix` and `inventory/networks.nix` by hand.

Expected output shape:

- `./topology-result/main.svg` — hosts, services, and the physical
  desktoptoodle/t320-0 direct link
- `./topology-result/network.svg` — one card per logical network
  (`direct-link`, `tailscale`, `yggdrasil-private`,
  `yggdrasil-public-peering`), each showing only the hosts and edges that
  inventory actually assigns to it

If a network or link looks wrong, check inventory first, not the topology
wiring — `lib/topology.nix` only reorganizes data that already lives in
`org.network.directLink` and `inventory/networks.nix`; see
[`docs/architecture/overview.md`](/work/flake/docs/architecture/overview.md#network-and-deployment-surfaces)
for exactly which field feeds which part of the diagram. To inspect what one
host resolved to without rendering:

```bash
nix eval .#nixosConfigurations.<host>.config.topology.self.interfaces \
  --apply 'ifaces: builtins.mapAttrs (_: i: { inherit (i) network addresses virtual physicalConnections; }) ifaces'
```

## Check The Live And Evaluated Kernel

```bash
uname -r
nix eval --raw .#nixosConfigurations.desktoptoodle.config.boot.kernelPackages.kernel.version
```

Use the first command to inspect the currently running kernel on the host, and
the second to confirm what the flake will deploy next.

For temporary CopyFail mitigation checks on hosts that blacklist `algif_aead`,
use:

```bash
lsmod | grep '^algif_aead ' || true
modprobe algif_aead
```

If the module is not already loaded, the `modprobe` command should fail on a
mitigated host.
