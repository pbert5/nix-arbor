# `system/workstation`

Interactive workstation system posture.

## Purpose

Provides the baseline interactive-machine system services expected for the
repo's workstation hosts.

## Main Effects

- enables NetworkManager
- enables Docker

## Current Children

- `system/workstation/gaming`

## Requirements

- requires `system`
- conflicts with `system/compute-worker`
- intended for `workstation` hosts
