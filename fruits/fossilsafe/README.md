# FossilSafe Fruit

This fruit vendors the local `pbert5/FOSSILSAFE` fork into the main flake so we
can iterate on the app, expose it through the primary dendritic resolver, and
still keep a focused local flake for package and dev-shell work.

## Layout

- `FOSSILSAFE/`
  Vendored fork source tree cloned from `https://github.com/pbert5/FOSSILSAFE`
- `flake.nix`
  Fruit-local flake for package builds and a focused development shell
- `nix/fossilsafe-package.nix`
  Nix package for the forked backend, frontend, CLI, and smoke test wrappers
- `nix/fossilsafe-module.nix`
  NixOS module that renders `config.json` from Nix and optionally runs the app
- `nix/ltfs-open.nix`
  IBM-compatible LTFS package used by FossilSafe

## Usage

```bash
nix develop ./fruits/fossilsafe
nix build ./fruits/fossilsafe#fossilsafe
```

The primary system flake now resolves this fruit from `fruits/` directly and
maps host-specific settings from `inventory/hosts.nix`.
