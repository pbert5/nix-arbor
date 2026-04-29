# Dendritic Nix Flake

This is an opinionated personal take on dendritic Nix for managing a small set
of machines with a shared inventory, reusable capability modules, and
host-specific overrides.

It is intentionally practical rather than pristine:

- the repo is organized around one real multi-machine setup
- design choices optimize for iterating on actual hardware
- some areas are heavily vibe-coded, but they are exercised on my own machines
  and kept under `nix flake check`

## What This Repo Is

- a `flake-parts`-based system flake
- passive registries for `dendrites/`, `fruits/`, `homes/`, and `hosts/`
- inventory-driven assembly for NixOS and Home Manager
- a place to experiment with storage, deployment, and homelab workflows

## Where To Start

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/dendritic-guide.md`](docs/dendritic-guide.md)
- [`docs/authoring-guide.md`](docs/authoring-guide.md)
- [`examples/demo-inventory/README.md`](examples/demo-inventory/README.md)

## Notes About This Public Mirror

This repo is generated from a private source repo.

- sensitive deployment data and keys are removed or replaced
- some example values are synthetic
- deprecated or personal-only experiment paths may be omitted from the mirror

## Quick Commands

```bash
nix flake show
nix flake check
```
