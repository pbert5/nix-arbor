# `base`

Core host baseline for this repo.

## Purpose

`base` is the shared foundation that most machines get through role selection.
It collects the common low-level leaves that make a host behave like one of the
repo's managed systems.

## What It Imports

- `leaves/system.nix`
- `leaves/boot-grub.nix`
- `leaves/nix-maintenance.nix`
- `leaves/services.nix`
- `leaves/terminal.nix`
- `leaves/clamav.nix`

## Main Effects

- enables Nix flakes and `nix-command`
- sets the repo timezone
- installs the shared overlay stack
- enables Fish
- enables OpenSSH
- injects leader deployer keys into `root` authorized keys
- enables automatic Nix GC and optimize jobs
- enables ClamAV services

## Selection

Usually selected indirectly through roles like `workstation` and
`compute-worker`.
