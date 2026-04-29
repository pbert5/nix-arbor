# `network`

Network overlay umbrella dendrite.

## Purpose

Parent branch for the repo's overlay and underlay networking surfaces.

## Current Children

- `network/tailscale`
- `network/yggdrasil-private`

## Selection

Most hosts do not select `network` directly. It is usually attached
automatically through `inventory/networks.nix`.
