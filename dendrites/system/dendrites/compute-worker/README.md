# `system/compute-worker`

Compute-worker system posture.

## Purpose

Represents hosts that should compose as compute workers rather than interactive
workstations.

## Current State

This dendrite is intentionally light right now. Its main value is architectural:

- marks the host as a compute-worker system class
- participates in composition validation
- conflicts with `system/workstation`

## Requirements

- requires `system`
- intended for `compute-worker` hosts
- currently marked `experimental`
