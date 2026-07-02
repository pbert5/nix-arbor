# `clusterctl` Reference

The flat, authoritative command list is
[`clusterctl-commands.md`](./clusterctl-commands.md). This page records shared
usage and the commands whose behavior needs more explanation.

Run the flake-pinned tool with:

```bash
nix run .#clusterctl -- [--flake PATH] <command> ...
```

The package exposes three policy-enforced entry points backed by the same
implementation:

- `clusterctl` performs operational changes and elevates only subprocesses
  explicitly declared as requiring local root.
- `clusterchk` permits read-only status, validation, and identity-matrix
  commands. Identity checks use existing local state without privileged fetch
  or status-cache writes.
- `clusterplan` permits read-only commands plus supported previews. It forces
  deploy, install, identity generation, and identity rotation into dry-run
  mode and disables publication.

For example:

```bash
nix run .#clusterchk -- registry status
nix run .#clusterplan -- deploy desktoptoodle
nix run .#clusterctl -- deploy desktoptoodle
```

Private keys retain stable ownership. A root-owned signing or SOPS key causes
only the signing/decryption subprocess to run through `sudo`; the surrounding
CLI, flake checkout, Git operations, and Nix evaluation remain owned by the
invoking user. `deploy --local-root` similarly elevates only the deploy
subprocess rather than re-executing the whole CLI as root.

Before local elevation, `clusterctl` performs non-interactive sudo checks and
reports whether the command is covered by command-specific `NOPASSWD` policy,
an existing sudo credential timestamp is being reused, or an authentication
prompt is expected. The checks neither invalidate cached credentials nor force
a new prompt.

Common registry options are:

- `--registry`, default `/var/lib/cluster-identity/registry`
- `--out`, default `/run/cluster-identity`
- `--policy`, default `/etc/cluster-identity/policy.json`

## Registry Status

```bash
clusterctl registry status
clusterctl registry status --node r640-0
```

Status reports materialized record counts, conflicts, accepted IPNS
checkpoints, CIDs and sequences, and the result of the latest fetch. It replaces
the former separate `identity status` view.

## Identity Rollout

```bash
clusterctl identity matrix
clusterctl identity generate-missing --dry-run
clusterctl identity generate-missing
clusterctl identity publish
```

`matrix` derives required identities from the normalized flake inventory.
`generate-missing` creates supported missing source records, and `publish`
turns the normalized identity ledger into signed registry events.

By default, `generate-missing` also publishes the records it creates. Generation
runs as the invoking user so checkout files retain their ownership. When the
registry, materialized output, or signing key is root-only, only the subsequent
`identity publish` phase is re-invoked through `sudo`. Use `--no-publish` when
you intentionally want to update the flake ledger without touching the live
registry.

## IPFS/IPNS Smoke Test

```bash
clusterctl identity smoke-test
clusterctl identity smoke-test \
  --verify-node r640-0 \
  --verify-node desktoptoodle
```

The smoke test publishes the current signed snapshot through IPFS/IPNS,
triggers follower fetches, and waits for each selected host to accept the exact
published CID and root sequence in its anti-rollback checkpoint. It does not
create synthetic identity events.

Options:

- `--verify-node HOST`, repeatable
- `--poll-seconds N`, default `90`
- `--poll-interval FLOAT`, default `2`
- `--snapshot-dir PATH`
- `--leader NAME`
- `--signing-key PATH`

## Internal Commands

Commands marked `INTERNAL` in `--help` are implementation interfaces for
activation and systemd:

- `registry ensure-v1`
- `registry fetch-ipfs`
- `registry snapshot`
- `registry publish-ipfs`
- `registry ipns-key ensure`

They remain callable for diagnostics, but they are not routine operator steps.

## Emergency Repairs

Commands marked `EMERGENCY REPAIR` bypass or reconstruct part of the normal
declarative workflow:

- `registry reconcile`
- `bundle emergency-publish`
- `host-age rotate`

Prefer `bundle seal` over `bundle emergency-publish`; the emergency command
transfers plaintext private key material over SSH.

## Deployment and VMs

```bash
clusterctl deploy r640-0 desktoptoodle t320-0
clusterctl deploy all --dry-run
nix run .#host-vm -- desktoptoodle --fresh
```

Named-host `deploy` resolves live identity candidates before invoking
deploy-rs. `deploy all` performs boot-critical preflight comparison first:
changed or unverifiable hosts use deploy-rs, while unchanged hosts retain
Colmena fan-out. VM launching belongs to the dedicated `host-vm` app and is no
longer a `clusterctl` command.
