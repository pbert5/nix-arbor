# `media/game-library`

Shared game library client mount and server export policy.

## Purpose

Mounts the repo-defined game library storage onto client hosts, prepares the
filesystem permissions around it, and optionally exports the backing dataset
from the source host.

## Main Effects

- creates the configured game-library group
- mounts the configured source at the configured mount point on client hosts
- installs tmpfiles rules for the mount point
- exports the configured backing path over NFS on hosts that enable
  `media/game-library/export`

## Inventory Inputs

Reads from `site.storage.gameLibrary`, including:

- group name and group ID
- mount point
- device/source
- filesystem type
- mount options
- backing local path
- NFS export hosts and export options

## Requirements

- requires `media`
