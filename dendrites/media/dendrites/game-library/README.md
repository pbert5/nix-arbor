# `media/game-library`

Shared game library mount and group policy.

## Purpose

Mounts the repo-defined game library storage onto a host and prepares the
filesystem permissions around it.

## Main Effects

- creates the configured game-library group
- mounts the configured source at the configured mount point
- installs tmpfiles rules for the mount point

## Inventory Inputs

Reads from `site.storage.gameLibrary`, including:

- group name and group ID
- mount point
- device/source
- filesystem type
- mount options

## Requirements

- requires `media`
