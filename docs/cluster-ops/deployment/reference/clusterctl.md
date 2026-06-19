# `clusterctl` Reference

This page documents the current `clusterctl` CLI surface from
[`tools/clusterctl/clusterctl/main.py`](/work/flake/tools/clusterctl/clusterctl/main.py).
Use it when you want the exact command groups and flags, especially for
deployment work.

Run the flake-pinned tool like this:

```bash
nix run .#clusterctl -- [--flake PATH] <command> ...
```

Global options:

- `--flake PATH`
  - flake root to evaluate; defaults to `.` or `CLUSTERCTL_FLAKE`

## Top-Level Commands

- `registry`
  - `init`, `validate`, `reconcile`, `materialize`, `sync`, `push`, `notify`,
    `status`, `remotes sync`, `resign-placeholders`
- `identity`
  - `publish`, `publish-public`, `publish-inventory`, `promote`, `burn`,
    `status`, `matrix`, `generate-missing`, `smoke-test`, `apply`
- `bundle`
  - `publish`, `seal`
- `receipt`
  - `write`, `collect`
- `deploy`
- `host-age`
  - `bootstrap`, `public`, `rotate`

## Common Registry Paths

Many subcommands share these options:

- `--registry`
  - defaults to `/var/lib/cluster-identity/registry`
- `--out`
  - defaults to `/run/cluster-identity`
- `--policy`
  - defaults to `/etc/cluster-identity/policy.json`

Signing-aware commands may also accept:

- `--signing-key PATH`
- `--signature`

## `deploy`

Usage:

```bash
nix run .#clusterctl -- deploy HOST [HOST ...]
```

Host selectors:

- `r640-0`
- `r640-0 desktoptoodle`
- `r640-0,desktoptoodle`
- `all`

Options:

- `hosts`
  - one or more host selectors; `all` expands to every exported inventory host
- `--out PATH`
  - materialized registry state used to resolve deployment candidates; defaults
    to `/run/cluster-identity`
- `--dry-run`
  - print candidate addresses, the selected target, and the generated
    `nix run .#deploy-rs -- .#HOST` command without executing it

Candidate order:

1. active Ygg address from `active.json`
2. staged Ygg address from `staged.json`
3. deprecated Ygg address from `deprecated.json`
4. fallback `targetHost` from `inventory/host-bootstrap.nix`
5. plain host name

Examples:

```bash
nix run .#clusterctl -- deploy r640-0
nix run .#clusterctl -- deploy r640-0 desktoptoodle t320-0
nix run .#clusterctl -- deploy all --dry-run
```

## `registry`

Shared options: `--registry`, `--out`, `--policy`

- `registry init`
  - `--no-commit`
- `registry validate`
- `registry reconcile`
- `registry materialize`
- `registry sync`
  - `--sync-remotes` / `--no-sync-remotes`
  - `--prune-remotes`
- `registry push`
  - `--remote NAME` repeatable
  - `--sync-remotes` / `--no-sync-remotes`
  - `--prune-remotes`
- `registry notify`
  - `--target HOST` repeatable
- `registry status`
- `registry remotes sync`
  - `--prune`
- `registry resign-placeholders`
  - `--signing-key PATH`
  - `--signature`
  - `--no-commit`

## `identity`

- `identity publish`
  - common registry options
  - `--service NAME` repeatable
  - `--node HOST` repeatable
  - `--generation N`
  - `--state STATE`
  - `--leader`
  - `--leader-key`
  - `--signing-key PATH`
  - `--signature`
  - `--allow-duplicate`
  - `--no-commit`
  - `--no-reconcile`
  - `--fetch` / `--no-fetch`
  - `--push` / `--no-push`
  - `--remote NAME` repeatable
  - `--notify`
- `identity publish-public NODE SERVICE`
  - common registry options
  - `--generation N` required
  - `--state STATE`, default `staged`
  - `--from-inventory`
  - `--allow-duplicate`
  - public-field flags: `--ssh-host-key`, `--yggdrasil-public-key`,
    `--yggdrasil-address`, `--deploy-host`, `--radicle-node-id`,
    `--git-annex-endpoint`
  - `--supersedes EVENT_ID` repeatable
  - `--leader`
  - `--leader-key`
  - `--signing-key PATH`
  - `--signature`
  - `--no-commit`
- `identity publish-inventory`
  - common registry options
  - `--service yggdrasil`
  - `--generation N` required
  - `--state STATE`, default `staged`
  - `--leader`
  - `--leader-key`
  - `--signing-key PATH`
  - `--signature`
  - `--allow-duplicate`
  - `--no-commit`
- `identity promote NODE SERVICE`
  - common registry options
  - `--generation N` required
  - `--leader`
  - `--leader-key`
  - `--signing-key PATH`
  - `--signature`
  - `--no-commit`
- `identity burn NODE SERVICE`
  - common registry options
  - `--generation N` required
  - `--fingerprint` required
  - `--reason` required
  - `--leader`
  - `--leader-key`
  - `--signing-key PATH`
  - `--signature`
  - `--no-commit`
- `identity status [NODE]`
  - common registry options
- `identity matrix`
  - `--node HOST` repeatable
  - `--service NAME` repeatable
  - `--only-missing`
  - `--json`
- `identity generate-missing`
  - common registry options
  - `--node HOST` repeatable
  - `--service NAME` repeatable
  - `--dry-run`
  - `--publish` / `--no-publish`
  - `--publish-push` / `--no-publish-push`
  - `--notify`
  - `--no-reconcile`
  - `--leader`
  - `--leader-key`
  - `--signing-key PATH`
  - `--signature`
  - `--no-commit`
- `identity smoke-test`
  - common registry options
  - `--node HOST` repeatable
  - `--verify-node HOST` repeatable
  - `--stress-rounds N`, default `3`
  - `--poll-seconds N`, default `90`
  - `--poll-interval FLOAT`, default `2.0`
  - `--leader`
  - `--leader-key`
  - `--signing-key PATH`
  - `--signature`
- `identity apply`
  - common registry options

## `bundle`

- `bundle publish NODE SERVICE`
  - `--generation N` required
  - `--source PATH` required
  - `--target-path PATH` required
- `bundle seal NODE SERVICE`
  - common registry options
  - `--generation N` required
  - `--source PATH` required
  - `--target-path PATH` required
  - `--recipient`
  - `--from-inventory`
  - `--leader`
  - `--leader-key`
  - `--signing-key PATH`
  - `--signature`
  - `--no-commit`

## `receipt`

- `receipt write`
  - common registry options
  - `--node HOST` required
  - `--service NAME` required
  - `--generation N` required
  - `--status`, default `node-activated`
  - `--activated`
  - `--signed-by-node`
  - `--signing-key PATH`
  - `--signature`
  - `--path PATH`
- `receipt collect NODE SERVICE`
  - `--generation N` required
  - `--registry PATH`, default `/var/lib/cluster-identity/registry`
  - `--no-commit`

## `host-age`

- `host-age bootstrap HOST`
  - `--source PATH`
  - `--target-path PATH`, default
    `/var/lib/cluster-identity/age/host.agekey`
- `host-age public HOST`
  - `--target-path PATH`, default
    `/var/lib/cluster-identity/age/host.agekey`
- `host-age rotate HOST`
  - `--target-path PATH`, default
    `/var/lib/cluster-identity/age/host.agekey`
