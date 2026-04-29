# Inventory Surfaces

This guide explains which inventory files matter for cluster operations and why
they are split apart.

## `inventory/hosts.nix`

Purpose:

- hand-authored host composition
- roles, networks, dendrites, fruits, users
- durable host facts and policy
- distributed-build client and builder policy under `org.nix`

This file is not the right place for an operator bootstrap tool to constantly
rewrite transport metadata.

## `inventory/host-bootstrap.nix`

Purpose:

- bootstrap target host or IP
- bootstrap SSH user
- optional deploy-rs SSH identity file path
- deployment transport preference
- deployment tags
- operator-capable marker

This is the operator-managed transport and rollout sidecar.

## `inventory/private-yggdrasil-identities.nix`

Purpose:

- enrolled Ygg public key
- expected Ygg IPv6 address

This is public cluster identity metadata, not private host-secret material.

## `inventory/networks.nix`

Purpose:

- network topology
- peer graph
- transport defaults
- overlay firewall defaults

This file describes the mesh. The identities file supplies the host-level
public identity facts that plug into that mesh.

## `inventory/keys/leaders/`

Purpose:

- trusted leader deployer public keys

Every host loads these into root SSH access through the base SSH leaf.
