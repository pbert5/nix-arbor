# Insurance Experiment

This experiment revives the earlier offline-insurance branch rooted at commit
`51128731525cdc8aedbdcec17f6d6816310d1e9f`, but keeps the workflow isolated
under `experiments/` and driven via `nix run`.

It snapshots a flake's locked inputs, mirrors the archived source trees into a
normal directory, refreshes git clones plus rolling bundle files for referenced
repos, and can optionally build and export a concrete closure such as a host's
`system.build.toplevel`.

The goal is to keep enough source and closure data around to rebuild the current
system later, while also inventorying the outputs exposed by referenced flakes.

## What it captures

- `nix flake metadata --json`
- `nix flake archive --json`
- refreshed git clones for flake-lock repos under `repos/`
- rolling single-file git bundles under `bundles/`
- plain snapshots of the main flake working tree and any local path inputs
- copied source trees for archived `/nix/store/...-source` paths
- a manifest summarising referenced flakes and their output surfaces
- live NixOS installer ISOs and checksum files for the derived release channels
- optional build closure data for a specific installable
- optional `file://` store export for that built closure

## Usage

Snapshot the main repo and capture the `desktoptoodle` system closure:

```bash
nix run ./experiments/insurance -- snapshot --flake /work/flake --nixos-host desktoptoodle
```

Also export the built closure into a local file-backed store mirror:

```bash
nix run ./experiments/insurance -- snapshot --flake /work/flake --nixos-host desktoptoodle --copy-store
```

Target an explicit installable instead:

```bash
nix run ./experiments/insurance -- snapshot --flake /work/flake --installable /work/flake#packages.x86_64-linux.fossilsafe
```

Skip package enumeration when you only want the locked sources:

```bash
nix run ./experiments/insurance -- snapshot --flake /work/flake --skip-packages
```

Mirror an extra repo and include giant package sets too:

```bash
nix run ./experiments/insurance -- snapshot --flake /work/flake \
  --extra-git-repo my-overlay=https://github.com/example/my-overlay.git \
  --include-large-package-sets
```

Skip live installer downloads when you only want source and closure capture:

```bash
nix run ./experiments/insurance -- snapshot --flake /work/flake --skip-live-install-tools
```

## Output layout

By default the experiment writes into `./insurance-output`:

- `metadata.json`
- `archive.json`
- `manifest.json`
- `isos/` with installer ISOs and `.sha256` checksum files
- `repos/` with refreshable git clones
- `bundles/` with rolling `.bundle` files
- `snapshots/` with plain copied working trees and path inputs
- `flake-outputs.json` when output enumeration is enabled
- `closure.json` when an installable is built
- `store-export/` when `--copy-store` is enabled
- `sources/` with mirrored source trees copied out of the Nix store

## Notes

- Very large inputs such as `nixpkgs` are intentionally skipped during package
  enumeration unless `--include-large-package-sets` is used, because otherwise
  the manifest turns into a small moon.
- `nix flake archive` can take a while the first time because it has to fetch
  every locked input.
- Git mirrors can also take a while the first time, especially for `nixpkgs`.
- Newly created files must be tracked in git before Nix flakes can see them.
