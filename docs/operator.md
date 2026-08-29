# Operator guide

This is the current operator surface. Commands below run the checked-out
manager through the flake; use `nix run .#arbor-manager -- ...` from the Arbor
root, or invoke `arbor-manager` directly when it is on `PATH`.

## Before deployment

Arbor Manager consumes an immutable deployment snapshot. It does not query the
old registry, connect to hosts, or make registry data authoritative. Confirm
the snapshot digest and inspect the proposed scope and plan:

```sh
nix run .#arbor-manager -- nodes list --snapshot deployment.json --scope selected --format table
nix run .#arbor-manager -- nodes list --snapshot deployment.json --scope accessible --format names
nix run .#arbor-manager -- machine inspect --snapshot deployment.json --name NAME
nix run .#arbor-manager -- deployment plan --snapshot deployment.json --format text
```

`nodes list` supports `all`, `local`, `selected`, `excluded`, `roots`,
`children`, `descendants`, `parents`, `ancestors`, `peers`, and `accessible`.
Use `--format json|table|names|ssh|colmena`; the latter two are display
projections only.

The current wrapper has no `tui` subcommand. There is no supported interactive
TUI entrypoint to document or rely on; use the explicit, reviewable commands
above.

## Access and external targets

These operations read JSON data files and redact secrets in output. Private
inputs must be regular files with mode `0600`, `0400`, `0640`, or `0440`.

```sh
nix run .#arbor-manager -- identity inspect --path identity.json
nix run .#arbor-manager -- external-target inspect --path targets.json --name NAME
nix run .#arbor-manager -- external-target manage --path targets.json \
  --runtime-executable ./runtime-adapter
```

`identity rotate` and target management require an executable runtime adapter;
the adapter receives the versioned JSON runtime contract. The manager never
turns an imported file into registry truth.

## Private recovery data

Inspect or export recovery data without printing private values. Import copies
the source with mode `0600`; review the destination and protect it outside the
repository:

```sh
nix run .#arbor-manager -- recovery inspect --path recovery.json
nix run .#arbor-manager -- recovery export --path recovery.json
nix run .#arbor-manager -- recovery import --path recovery.json --output /secure/path/recovery.json
```

Recovery approval, multi-host recovery, and secret release remain runtime or
external procedures. Never commit private keys, tokens, recovery material, or
generated secret files.

To install an identity file into a protected destination, use
`identity import --path SOURCE --output DEST`. To rotate an identity, use
`identity rotate --path SOURCE --runtime-executable ADAPTER`; rotation is
delegated to that runtime adapter and fails closed when it is absent.

## Health and deployment

```sh
nix run .#arbor-manager -- doctor --format text
nix run .#arbor-manager -- deployment apply --snapshot deployment.json --dry-run
nix run .#arbor-manager -- deployment apply --snapshot deployment.json \
  --acknowledgement DIGEST --backend-executable ./deploy-adapter \
  --receipt deployment-receipt.json
```

`doctor` reads `/run/arbor/doctor/status.json` by default and exits non-zero
unless healthy; override it with `--status FILE`. A real apply requires the
snapshot acknowledgement digest (or token) and an explicit adapter. The
adapter is called once per node in each immutable phase; it is responsible for
SSH or Colmena execution. Use `--resume RECEIPT` only with a receipt bound to
the same snapshot and acknowledgement.

For standard NixOS switching, build and inspect first, then perform the
operator-approved action:

```sh
nix build .#nixosConfigurations.NAME.config.system.build.toplevel
nixos-rebuild switch --flake .#NAME --target-host HOST
```

## Migration dispositions

Read [legacy machine dispositions](migrations/legacy-machine-disposition.md)
and the [r640-0 cutover](migrations/r640-0-cutover.md) before touching a
legacy host. The [migration matrix](arbor-registry-migration-matrix.md) records
which capabilities moved, were dropped, or remain deferred. Identity-only and
template-only records are not active host configurations; reactivation needs a
separately reviewed profile and hardware module.
