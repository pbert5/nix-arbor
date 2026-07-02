# `storage/zfs`

ZFS host storage branch.

## Purpose

Adds the baseline host configuration required for a ZFS-managed system.

## Main Effects

- enables ZFS as a supported filesystem
- adds the configured pool to `boot.zfs.extraPools`
- explicitly preserves forced root-pool import behavior across the NixOS 26.05
  upgrade
- sets `networking.hostId` when provided

## Inventory Inputs

- `facts.storage.zfs.poolName`
- `facts.storage.zfs.rootMountPoint`
- `facts.hostId`

## Requirements

- requires `storage`
- intended for `workstation` and `compute-worker` hosts
