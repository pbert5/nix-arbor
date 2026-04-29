# Inventory Schema Reference

This page is the field-level reference for the cluster-ops inventory surfaces.

## `inventory/host-bootstrap.nix`

Per-host operator-side transport metadata.

### `targetHost`

Bootstrap endpoint for reaching the host before or during normal deployment.

Typical values:

- raw management IPv4 address
- Tailscale IPv4 address
- DNS name if you have one

### `sshUser`

The SSH login user for bootstrap and deployment. In the current cluster model
this is normally `root`.

### `identityFile`

Optional local private key path to pass to generated deploy-rs SSH options for
that target.

The repo stores the path only. The private key must exist on the operator
machine running deploy-rs.

### `deploymentTransport`

Which generated transport should be preferred for normal deployment.

Current values in use:

- `bootstrap`
- `privateYggdrasil`

### `deploymentTags`

Free-form operator tagging for deployment grouping or future rollout logic.

### `operatorCapable`

Marks a host as a leader-capable operator machine.

Operationally this means:

- it is expected to be a cluster control point
- its deployer key should exist under `inventory/keys/leaders/`

## `inventory/private-yggdrasil-identities.nix`

Per-host public Ygg identity metadata.

### `address`

The host's expected Ygg IPv6 address derived from its public identity.

### `publicKey`

The host's Ygg public key used for peer identity pinning and allowlists.

## `inventory/hosts.nix`

This remains the durable host-composition surface.

The bootstrap tool should not use it as a scratchpad for transport state.

Relevant fields for cluster ops include:

- `networks`
- `publicYggdrasil`
- `roles`
- `dendrites`
- `facts`
- `org.*`

### `org.nix.distributedBuilds`

Host-local coordinator settings for the `system/distributed-builds` dendrite.

Important fields:

- `builders`
  inventory host names to use as remote build machines
- `sshKey`
  local private key path used by the coordinator's Nix daemon
- `buildersUseSubstitutes`
  optional override for `nix.settings.builders-use-substitutes`

### `org.nix.buildMachine`

Host-local scheduler hints used when another machine lists this host as a
builder.

Important fields:

- `maxJobs`
- `speedFactor`
- `systems`
- `supportedFeatures`
- `mandatoryFeatures`
- `publicHostKey`

## `inventory/networks.nix`

This is where topology and policy live.

Relevant cluster-op concerns include:

- overlay listener endpoints
- peer graph
- firewall defaults
- per-node overlay policy

## `inventory/keys/leaders/`

Each regular file in this directory is treated as a trusted leader deployer key
source for root SSH access across the fleet.
