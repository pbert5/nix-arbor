# `storage/zfs`

ZFS host storage branch.

## Purpose

Adds the baseline host configuration required for a ZFS-managed system.

## Main Effects

- enables ZFS as a supported filesystem
- adds the configured pool to `boot.zfs.extraPools`
- sets `networking.hostId` when provided

## Inventory Inputs

- `facts.storage.zfs.poolName`
- `facts.storage.zfs.rootMountPoint`
- `facts.hostId`

## Requirements

- requires `storage`
- intended for `workstation` hosts
