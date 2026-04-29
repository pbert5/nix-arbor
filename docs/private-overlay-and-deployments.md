# Private Overlay And Deployments

This document covers the currently implemented subset of
[`plans/true_distribuited_cluster/ideas.md`](/work/flake/plans/true_distribuited_cluster/ideas.md).

It documents what is already real in the primary flake, what knobs exist in
inventory, and which parts of the original plan are still future work.

## What Is Implemented

The main flake now implements these parts of the plan:

- one private Yggdrasil mesh defined from `inventory/networks.nix`
- selective Tailscale on hosts that need cross-network bridging
- an inventory-driven Yggdrasil dendrite (`network/yggdrasil-private`)
- generated deployment surfaces for Colmena and deploy-rs
- a hardened host-firewall model for the private overlay
- evaluation and VM smoke tests for the new network/deployment surfaces

The flake does **not** currently implement every idea from the plan. Public
Yggdrasil sidecars, private binary cache services over Ygg, and Radicle
integration are still future work.

## Current Topology Model

The canonical topology data lives in
[`inventory/networks.nix`](/work/flake/inventory/networks.nix).

Tracked Ygg identity data now lives separately in
[`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
so the bootstrap workflow can update public metadata without rewriting the
whole topology file.

Operator-managed bootstrap and deployment metadata lives in
[`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix).
That file tracks bootstrap targets, SSH bootstrap users, operator-capable
markers, deployment tags, and whether rollout should currently prefer bootstrap
transport or private Ygg transport.

Each network definition now declares the dendrite that implements it, and hosts
opt into networks explicitly from
[`inventory/hosts.nix`](/work/flake/inventory/hosts.nix) using
`networks = [ ... ]`.

Current network definitions:

- `tailscale`
  - dendrite: `network/tailscale`
- `privateYggdrasil`
  - dendrite: `network/yggdrasil-private`
  - `public = false` by default until fixed public-key identity is modeled in
    inventory

Current shared defaults:

- transport scheme: `tls`
- transport interface: `tailscale0`
- listener port: `14742`
- overlay interface name: `ygg0`
- `NodeInfoPrivacy = true`
- multicast disabled by default
- persistent keys enabled by default

Current site-wide firewall defaults:

- firewall enforcement enabled
- reverse-path filtering enabled (`checkReversePath = true`)
- listener port opening on the underlay enabled
- overlay TCP/UDP allowlists default to empty lists
- peer-source filtering defaults to off until all required peer identities are
  enrolled

## Host Roles And Selection

The network layer is now attached explicitly by host network membership instead
of role-driven dendrite attachment.

- `inventory/hosts.nix`
  - `dev-machine`, `r640-0`, and `desktoptoodle` opt into
    `privateYggdrasil` and `tailscale`
  - `compute-worker` opts into `privateYggdrasil` only
  - every current host also sets `publicYggdrasil = false`
- `inventory/roles.nix`
  - roles continue to attach shared base/system behavior, but not the private
    Yggdrasil network dendrite

That means the current intent is:

- private Yggdrasil is an explicit per-host network selection across managed
  nodes
- Tailscale is only the underlay/bridge on selected exported machines
- public Yggdrasil stays disabled until the repo carries fixed identities and a
  clearer trust model

## Private Yggdrasil Dendrite

The implementation lives in
[`dendrites/network/dendrites/yggdrasil-private/yggdrasil-private.nix`](/work/flake/dendrites/network/dendrites/yggdrasil-private/yggdrasil-private.nix).

It currently does all of the following from inventory:

- enables Yggdrasil only on hosts with a matching node definition
- derives static peer URIs from the node peer graph
- supports transport schemes such as `tls`, `tcp`, `ws`, `wss`, or `quic`
- configures `IfName`, `Listen`, `Peers`, `NodeInfoPrivacy`, and related
  settings from site defaults plus per-node overrides
- supports optional `AllowedPublicKeys` allowlists derived from peer public keys
- appends `?key=<peer-public-key>` to peer URIs when a peer identity is enrolled
- can restrict all overlay input on `ygg0` to explicit peer source addresses
  when `firewall.overlay.restrictToPeerSources = true`
- optionally emits `networking.hosts` aliases for overlay addresses

### Overlay Alias Support

The module can generate pseudo-DNS entries like:

```nix
networking.hosts."200:1111:2222:3333::1" = [ "alpha-ygg" "alpha-overlay" ];
```

That support is implemented, and it now activates for whichever hosts have
addresses enrolled in
[`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix).
Hosts without enrolled addresses simply do not get an overlay alias yet.

## Firewall Model

The private overlay firewall model is intentionally stricter than just trusting
Yggdrasil peers.

Current behavior:

- enabling `network/yggdrasil-private` requires the host firewall to remain on
- the overlay interface (`ygg0` by default) gets explicit TCP/UDP allowlists
- the listener underlay interface (`tailscale0` by default) only opens the
  configured Yggdrasil listener port
- when `firewall.overlay.restrictToPeerSources = true`, the host injects an
  IPv6 source filter on `ygg0` so only explicit peer addresses can initiate
  overlay traffic
- `trustedInterfaces` is rejected for both:
  - the overlay interface
  - the Ygg listener underlay interface

This matters because a TUN-enabled Yggdrasil instance is routable IPv6 space,
so `AllowedPublicKeys` alone is not enough to protect services exposed over the
overlay.

### Current Default Policy

By default, overlay service exposure is deny-by-default.

To allow a service over the private overlay, define it explicitly under a host
or site firewall stanza, for example:

```nix
firewall.overlay.allowedTCPPorts = [ 18080 ];
```

That pattern is covered by the eval and smoke checks already shipped in the
flake.

### Peer Identity Lockdown

Strict overlay contact control needs more than port allowlists.

To fully lock a host down so only explicit peers can reach it over Ygg:

- enroll each peer's `address` and `publicKey`
- rebuild the enrolled hosts so `AllowedPublicKeys` and peer URI pinning take
  effect
- enable `firewall.overlay.restrictToPeerSources = true` for hosts that should
  reject all non-peer traffic on `ygg0`

That strict mode validates that every declared peer already has both identity
fields enrolled before evaluation succeeds.

## Identity Bootstrap Workflow

The flake now ships a bootstrap helper:

```bash
nix run .#yggdrasil-bootstrap -- --host r640-0 --target 100.64.0.10
```

There is also an alias that matches the operator workflow name more closely:

```bash
nix run .#bootstrap-host -- --host r640-0 --target 100.64.0.10
```

What it does:

- connects over SSH, using `root` by default
- ensures `/var/lib/yggdrasil/keys.json` exists on the target
- derives the target host's Ygg public key and Ygg address
- rewrites
  [`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
  in a canonical format with the updated public metadata
- updates
  [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
  with bootstrap target, SSH user, deployment transport, deployment tags, and
  operator-capable metadata
- can optionally create a Git commit and trigger a first deployment using the
  flake-pinned `deploy-rs` or `colmena` apps

What it does not do:

- it does not automatically rewrite `inventory/hosts.nix`
- it does not force peer-source filtering on by itself
- it does not silently redeploy peers unless you ask for that explicitly

That separation is deliberate. Enrollment updates public metadata. Rebuilds and
policy changes stay explicit.

### Normal Fleet Deployment After Enrollment

The intended two-layer workflow is now:

1. use `bootstrap-host` or `yggdrasil-bootstrap` to enroll or refresh the host
   identity over the bootstrap endpoint
2. set `deploymentTransport = "privateYggdrasil"` for hosts that should now be
   managed over Ygg
3. redeploy the enrolled host, then redeploy peers that should trust the new
   identity
4. use the flake-pinned `deploy-rs` and `colmena` apps for ordinary rollout

That keeps initial enrollment manual and explicit, while making normal
post-enrollment management a standard flake deployment workflow.

### Leader Root Access

Trusted leader-machine deployer keys now live under:

```text
inventory/keys/leaders/
```

The base SSH layer reads every regular file in that directory and merges those
keys into `users.users.root.openssh.authorizedKeys.keys` on every host.

That means trusted leader machines can act as Colmena or deploy-rs deployers
against the whole fleet, including each other.

## Deployment Outputs

The flake now publishes inventory-generated deployment outputs.

Implementation entrypoint:

- [`modules/flake-parts/deployments.nix`](/work/flake/modules/flake-parts/deployments.nix)

Generation helper:

- [`lib/deployments.nix`](/work/flake/lib/deployments.nix)

Published outputs:

- `flake.colmena`
- `flake.colmenaHive`
- `flake.deploy`

These are generated only for exported hosts.

At the time of writing, that means:

- `dev-machine`
- `r640-0`
- `desktoptoodle`

`compute-worker` is intentionally excluded because `exported = false`.

## How Targets Are Resolved

Both deployment surfaces derive their targets from the same inventory data.

Workstation Home Manager configs use that same inventory for interactive SSH.
The shared `homes/shared/ssh` module creates user SSH match blocks from
[`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
and private Yggdrasil aliases, including configured `identityFile` values when
present. That keeps `ssh r640-0`, `ssh r640-0-ygg`, and deployment identity
paths pointed at one declarative source.

Base resolution order:

1. `org.deployment.targetHost`
2. the enrolled Ygg address when `inventory.hostBootstrap.<host>.deploymentTransport = "privateYggdrasil"`
3. `inventory.hostBootstrap.<host>.targetHost`
4. `inventory.networks.privateYggdrasil.nodes.<host>.deployHost`
5. `inventory.networks.privateYggdrasil.nodes.<host>.endpointHost`
6. the host attribute name

Base defaults:

- `targetPort = 22`
- `sshUser = inventory.hostBootstrap.<host>.sshUser or "root"`
- `targetUser = "root"`

Tags are generated automatically from:

- host name
- bootstrap deployment tags from `inventory.hostBootstrap.<host>.deploymentTags`
- `operator-capable` when `inventory.hostBootstrap.<host>.operatorCapable = true`
- a `transport-…` tag derived from the resolved deployment transport
- roles
- selected dendrites
- selected fruits
- any `org.deployment.tags`

### Colmena Surface

`flake.colmena` is the raw generated host map.

`flake.colmenaHive` is the direct Colmena flake surface created with
`inputs.colmena.lib.makeHive`.

Per-host Colmena overrides live under:

```nix
org.deployment.colmena
```

Currently supported override fields are:

- `targetHost`
- `targetPort`
- `targetUser`
- `tags`
- `allowLocalDeployment`
- `buildOnTarget`
- `replaceUnknownProfiles`

### deploy-rs Surface

`flake.deploy` is generated in deploy-rs format.

Each exported host currently gets one generated profile:

- `profiles.system`

That profile points at the already-built NixOS system for the host using
`deploy-rs.lib.<system>.activate.nixos`.

Per-host deploy-rs overrides live under:

```nix
org.deployment.deployRs
```

Currently supported override fields are:

- `hostname`
- `targetHost`
- `targetPort`
- `sshUser`
- `user`
- `targetUser`
- `profilesOrder`
- `sshOpts`
- `profilePath`
- `activationTimeout`
- `autoRollback`
- `confirmTimeout`
- `fastConnection`
- `interactiveSudo`
- `magicRollback`
- `remoteBuild`
- `sudo`
- `tempPath`

When not overridden, deploy-rs keeps its own normal defaults such as magic
rollback behavior.

## Checks And Validation

The current check set includes network and deployment coverage:

- `network-overlay-eval`
  - validates inventory wiring and firewall semantics
- `yggdrasil-private-smoke`
  - boots VMs, forms a private Ygg mesh, and checks allow-vs-block behavior on
    overlay ports
- `deployment-targets-eval`
  - checks generated deployment targets exist for every exported host
- `deploy-activate`
- `deploy-schema`

Inventory validation also now checks that:

- every declared network has an explicit backing dendrite
- every private Ygg node maps to a known host
- peer references point at known hosts
- hosts selecting `privateYggdrasil` actually have a node definition
- hosts cannot opt into `publicYggdrasil` while the site-level network
  definition keeps it disabled

## Operator Notes

Useful inspection commands from the repo root:

```bash
nix eval --apply 'x: builtins.attrNames (builtins.removeAttrs x ["meta"])' .#colmena --json
nix eval '.#deploy.nodes.dev-machine' --json
nix eval --apply 'x: builtins.attrNames x' .#checks.x86_64-linux --json
```

If you change deployment generation or add new deployment-specific files,
remember that flakes ignore untracked files until they are staged.

## Still Planned

These plan items are still not implemented in the primary flake:

- a separate public Yggdrasil sidecar/namespace model for workstations once
  fixed keys and inventory-backed identity are modeled
- private binary cache serving over the Ygg overlay
- Radicle integration for repo distribution across the private mesh

If those land later, they should extend this doc instead of leaving the details
only in the original plan note.
