# Cluster Ops Architecture

This repo treats cluster operations as a separation of concerns problem.

The important split is:

- declarative host composition lives in hand-authored inventory and dendrites
- operator-managed transport and enrollment state lives in sidecar inventory
- private host secrets stay on the host and do not get committed into the repo

## The Two Layers

### Layer 1: Bootstrap

Bootstrap is the one manual trust handoff.

Inputs:

- host name
- raw target IP or other bootstrap endpoint
- SSH identity file
- optional transport and rollout flags

Outputs:

- an enrolled Ygg public key
- an enrolled Ygg IPv6 address
- updated operator-side inventory
- optionally a first deployment

Bootstrap is intentionally not hidden inside `colmena` or `deploy-rs` because
it is not just "deploy config"; it is "reach a raw machine, establish durable
identity, and record that identity back into the source of truth".

### Layer 2: Normal Fleet Operations

After enrollment, normal operations should be inventory-driven.

That means:

- deploy from trusted leader machines
- use generated deploy targets
- prefer private Ygg for east-west cluster management
- roll trust changes through the fleet by redeploying the relevant nodes

## Trust Boundaries

### Trusted Leaders

Trusted leaders are allowed to deploy as `root` to all managed machines.

Today those are:

- `desktoptoodle`
- `r640-0`

Their deployer public keys live in:

- [`inventory/keys/leaders/`](/work/flake/inventory/keys/leaders)

Those keys are distributed to every host via:

- [`dendrites/base/leaves/services.nix`](/work/flake/dendrites/base/leaves/services.nix)

### Managed Cluster Nodes

Managed nodes may:

- participate in the private Ygg mesh
- accept deployments
- know the public identity of peers they are configured to trust

Managed nodes should not:

- hold other hosts' private Ygg keys
- autonomously approve new hosts into inventory

### Raw Targets

Raw targets are machines reachable by bootstrap transport but not yet enrolled.

They become ordinary cluster nodes only after:

1. identity generation or discovery
2. inventory update
3. deployment

## Inventory Ownership

These surfaces intentionally have different jobs:

- [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix)
  host composition, dendrites, roles, durable policy
- [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
  operator-managed bootstrap target, deploy transport, rollout tags
- [`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
  enrolled public Ygg identities
- [`inventory/networks.nix`](/work/flake/inventory/networks.nix)
  topology, peer graph, overlay firewall policy

That split is deliberate. The bootstrap tool is allowed to edit operator-owned
surfaces, but it should not rewrite hand-authored host composition.

## Why Host-Generated Ygg Keys

The current design prefers:

- host-generated Ygg private keys
- centrally recorded Ygg public keys

This gives us:

- stable host identity without shipping private keys through the repo
- deterministic cluster trust built from public metadata
- a smaller blast radius if the deploy source is compromised

## Why Trust Changes Need Rollout

New peer trust is not magic and not gossip-driven in this repo.

If `r640-0` gets enrolled today, other machines only learn that new public key
after they receive updated config derived from inventory.

That is why enrollment and trust propagation are separate operational steps.
