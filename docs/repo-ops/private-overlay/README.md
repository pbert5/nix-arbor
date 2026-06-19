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

## Read Next

- [`network-and-firewall.md`](./network-and-firewall.md)
- [`bootstrap.md`](./bootstrap.md)
- [`deployment-surfaces.md`](./deployment-surfaces.md)
