# Public Export Workflow

This repo now supports generating a separate public mirror from an allowlisted
subset of the private flake.

The intent is:

- keep the private repo as the source of truth
- generate a separate public repo from it
- replace or remove known sensitive surfaces during export
- review the generated diff before pushing it to GitHub

This is intentionally a mirror workflow, not a "publish a cleaned branch from
the private repo" workflow.

## Command

Run the exporter from the private repo root:

```bash
nix run .#public-export -- --destination ../flake-public
```

That command:

- copies only Git-tracked files from the allowlisted top-level repo paths
- removes known private-only paths such as `inventory/keys/`
- overlays a small set of public-safe replacements
- redacts known patterns like local home paths, bootstrap IPs, hashed
  passwords, deploy key paths, and tape device serial paths
- anonymizes user names in human-facing docs and examples
- refreshes `flake.lock` in the destination when `nix` is available
- initializes a Git repository in the destination when one does not already
  exist
- stages the exported files so the destination flake evaluates immediately

To preview without writing files:

```bash
nix run .#public-export -- --destination ../flake-public --dry-run
```

To skip lock refresh:

```bash
nix run .#public-export -- --destination ../flake-public --skip-lock-refresh
```

To leave Git initialization to a separately cloned public repo:

```bash
nix run .#public-export -- --destination ../flake-public --skip-git-init
```

## Repo Layout

The export logic lives in:

- [`bootstrap/public-export.py`](/work/flake/bootstrap/public-export.py)
- [`public-export/export-config.json`](/work/flake/public-export/export-config.json)
- [`public-export/overlay/`](/work/flake/public-export/overlay)

`export-config.json` is the policy surface:

- `include_paths`
  - top-level repo content allowed into the public mirror
- `exclude_paths`
  - copied paths that must be removed from the public mirror
- `literal_replacements`
  - exact string rewrites
- `regex_replacements`
  - text redactions applied across copied UTF-8 files

The overlay directory contains files that should be replaced wholesale in the
public mirror, such as:

- a public-safe `flake.nix` without the local `/etc/nixos` path input
- empty Yggdrasil identity data
- bootstrap metadata with no real target hosts or deploy keys
- a public-facing top-level `README.md`
- a small `examples/demo-inventory/` reference tree

## Review Flow

After export:

```bash
cd ../flake-public
git status --short
git diff --stat
git diff
```

Before first push, manually spot-check these surfaces:

- `inventory/`
- `docs/`
- `hosts/`
- `README.md`
- `flake.nix`

If you add a new private file, private inventory surface, new credentials
workflow, or new host-specific operational doc in the private repo, update
`public-export/export-config.json` or `public-export/overlay/` in the same
change.

## Limits

This exporter is meant to make the safe path easy, not to replace judgment.

You should still:

- rotate any secrets that were ever committed before publishing
- review each generated export before push
- prefer example values over real environment values when adding new public
  docs or config surfaces
