# Nix Arbor

Nix Arbor is the composition flake for the independently versioned Nix
components used to build its machines. It is not a live registry, secret store,
or deployment controller. The committed machine files are build inputs; live
authority, private recovery material, and target state stay outside Git.

## Operator entrypoint

Start with [the operator guide](docs/operator.md). It covers the current
`arbor-manager` CLI, offline inspection, access and external targets, private
recovery-data handling, health checks, migration dispositions, and deployment.

For a development shell:

```sh
nix develop
```

For ordinary checks and formatting:

```sh
nix flake check
nix fmt
```

The machine inventory is under `config/machines/`. Build a configuration with
`nix build .#nixosConfigurations.<name>.config.system.build.toplevel`; apply it
only after the operator checks in [docs/operator.md](docs/operator.md).

## Project map

- `config/` — local machine facts and trusted composition
- `packages/` — independently versioned component flakes
- `docs/` — architecture, operations, and migration records
- `cheats/` — Navi learning and command reference

The remote flake inputs are reproducible defaults. Local component checkouts
under `packages/` are optional development overrides; see [DEV.md](DEV.md).

Architecture details are in [docs/architecture.md](docs/architecture.md) and
the registry boundary in [docs/arbor-registry-architecture.md](docs/arbor-registry-architecture.md).
