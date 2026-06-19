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

Preview without changing anything:

```bash
nix run .#clusterctl -- deploy all --dry-run
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

## Smoke-Test Rollout

Run the live smoke test on the operator-capable hosts:

```bash
nix run .#clusterctl -- identity smoke-test
```

Include the whole fleet as rollout subjects while still verifying on the easy
Tailscale-access leaders:

```bash
nix run .#clusterctl -- identity smoke-test --node all --verify-node r640-0 --verify-node desktoptoodle
```

## Good Defaults

- Start with `identity matrix --only-missing` if you want to know what is out of date.
- Run `identity generate-missing --node all` when rebuild warnings say a host is missing identities.
- Run `identity smoke-test` after transport or registry changes when you want a real end-to-end confidence check.
- Run `deploy all` after inventory or module changes when you want the fleet converged.

See also:

- [`command-reference.md`](/work/flake/docs/cluster-ops/reference/command-reference.md)
- [`../identity/README.md`](/work/flake/docs/cluster-ops/identity/README.md)
