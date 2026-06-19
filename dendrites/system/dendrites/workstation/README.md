# `system/workstation`

Interactive workstation system posture.

## Purpose

Provides the baseline interactive-machine system services expected for the
repo's workstation hosts.

## Main Effects

- enables NetworkManager
- enables Docker and pins the maintained `docker_29` package line
- enables QMK keyboard support
- installs VIA udev rules so compatible keyboards are accessible without manual
	permissions hacks
- installs the flake-pinned `nixard` package explorer

## Current Children

- `system/workstation/gaming`

## Requirements

- requires `system`
- conflicts with `system/compute-worker`
- intended for `workstation` hosts
