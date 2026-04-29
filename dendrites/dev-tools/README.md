# `dev-tools`

Small system-level developer tooling baseline.

## Purpose

Installs a handful of CLI tools that are useful across managed machines,
especially operator and workstation hosts.

## Main Effects

Adds these packages to `environment.systemPackages`:

- `curl`
- `git`
- `ssh-import-id`
- `tailscale`
- `wget`
- `ripgrep`

## Selection

Usually selected by the `workstation` role.
