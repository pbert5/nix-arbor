# clusterctl Quick Reference

Use this page first for the normal operator path.

Current host names:

- `r640-0`
- `desktoptoodle`
- `t320-0`

Selector patterns:

- one host: `r640-0`
- several hosts as separate args: `r640-0 desktoptoodle`
- several hosts as a comma list: `r640-0,desktoptoodle`
- the whole fleet: `all`

For commands that take `--node`, the same shapes work:

- `--node r640-0`
- `--node r640-0 --node desktoptoodle`
- `--node r640-0,desktoptoodle`
- `--node all`

## Deploy

Deploy one host:

```bash
nix run .#clusterctl -- deploy r640-0
```

Deploy several hosts:

```bash
nix run .#clusterctl -- deploy r640-0 desktoptoodle
```

Deploy the whole fleet:

```bash
nix run .#clusterctl -- deploy all
```

Boot-critical or unverifiable hosts are automatically removed from Colmena
fan-out and routed through deploy-rs.

Preview without changing anything:

```bash
nix run .#clusterctl -- deploy all --dry-run
```

## Interactive VM

Launch the `desktoptoodle` playtest VM:

```bash
nix run .#host-vm -- desktoptoodle
```

Start clean if you want to throw away the current qcow state:

```bash
nix run .#host-vm -- desktoptoodle --fresh
```

## Identity Matrix

Show the full desired-vs-present matrix:

```bash
nix run .#clusterctl -- identity matrix
```

Show only gaps:

```bash
nix run .#clusterctl -- identity matrix --only-missing
```

Scope to one host or service:

```bash
nix run .#clusterctl -- identity matrix --node r640-0
nix run .#clusterctl -- identity matrix --service git-annex
```

Show more or fewer burned live records per cell. The default is the latest two
burns; use a negative value for unlimited history:

```bash
nix run .#clusterctl -- identity matrix --burn-limit 5
nix run .#clusterctl -- identity matrix --burn-limit -1
```

Use the old ledger-only active display without status IPNS acknowledgement:

```bash
nix run .#clusterctl -- identity matrix --no-status-ack
```

With status acknowledgement enabled, `gN/au` means the ledger says active but
the target's signed status IPNS record did not confirm it, `gN/a` means the
target confirmed it, and `gN/aa` means every reachable peer status also agrees.

## Generate Missing Identities

Generate every missing identity the inventory implies:

```bash
nix run .#clusterctl -- identity generate-missing --node all
```

Generate only one host's missing identities:

```bash
nix run .#clusterctl -- identity generate-missing --node t320-0
```

Generate only one service across the fleet:

```bash
nix run .#clusterctl -- identity generate-missing --node all --service git-annex
```

Preview the changes first:

```bash
nix run .#clusterctl -- identity generate-missing --node all --dry-run
```

The command writes generated source records as the invoking user, then
automatically uses `sudo` for only the publication phase when the live registry
or signing key is root-only. Pass `--no-publish` to stop after updating the
declarative source ledger.

## Rotate An Identity

Replace one existing identity in the inventory source ledger with the next
generation:

```bash
nix run .#clusterctl -- identity rotate r640-0 yggdrasil
```

Preview without changing the ledger:

```bash
nix run .#clusterctl -- identity rotate r640-0 yggdrasil --dry-run
```

For `host-age`, the command updates `inventory/keys/host-age-recipients.nix`
after replacing the target host key.

The new generation is one higher than the highest generation known from the
flake ledger, materialized live state, or accepted registry events. Publication
also burns stale same-leader live claims that are absent from inventory or
older than a rotated fingerprint. Guarded services such as `host-age`,
`ssh-host`, and IPNS identities are skipped unless you pass
`--burn-guarded-stale`.

## Smoke-Test Rollout

Run the live smoke test on the operator-capable hosts:

```bash
nix run .#clusterctl -- identity smoke-test
```

Select the hosts whose accepted IPNS checkpoints must converge:

```bash
nix run .#clusterctl -- identity smoke-test --verify-node r640-0 --verify-node desktoptoodle
```

## Good Defaults

- Start with `identity matrix --only-missing` if you want to know what is out of date.
- Run `identity generate-missing --node all` when rebuild warnings say a host is missing identities.
- Run `identity smoke-test` after transport or registry changes when you want a real end-to-end confidence check.
- Run `deploy all` after inventory or module changes when you want the fleet converged.

See also:

- [`command-reference.md`](/work/flake/docs/cluster-ops/reference/command-reference.md)
- [`../identity/README.md`](/work/flake/docs/cluster-ops/identity/README.md)
