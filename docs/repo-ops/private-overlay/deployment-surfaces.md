# Deployment Surfaces

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

- `r640-0`
- `desktoptoodle`
- `t320-0`

Retired records are kept under `inventory/deprecated/` and are not part of the
evaluated deployment surfaces.

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
- selected service capability flags
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
nix eval '.#deploy.nodes.r640-0' --json
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
