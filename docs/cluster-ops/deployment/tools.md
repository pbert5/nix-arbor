# Deployment Tools

After a host is enrolled, normal operations should use the flake-generated
deployment surfaces and flake-pinned tool binaries.

## `clusterctl deploy`

Run:

```bash
nix run .#clusterctl -- deploy r640-0
```

Use it for:

- normal one-host deploys
- normal multi-host deploys
- dry-running the current deploy target resolution before a risky rollout

Why:

- it wraps the flake-pinned `deploy-rs` command instead of relying on a shell-global install
- it prints every candidate target before choosing one
- it prefers live identity-backed Ygg targets before falling back to bootstrap metadata

Useful forms:

```bash
nix run .#clusterctl -- deploy r640-0 desktoptoodle
nix run .#clusterctl -- deploy r640-0,desktoptoodle
nix run .#clusterctl -- deploy all
nix run .#clusterctl -- deploy all --dry-run
```

Important options:

- `hosts`
  - accepts separate args, comma lists, or `all`
- `--dry-run`
  - prints the candidate list, the selected target, and the `deploy-rs` command
    without executing it
- `--out PATH`
  - reads materialized identity state from a different directory instead of the
    default `/run/cluster-identity`

## deploy-rs

Run:

```bash
nix run .#deploy-rs -- .#r640-0
```

Use it for:

- networking changes
- SSH changes
- firewall changes
- other risky host changes where rollback behavior matters

Why:

- it is the safer tool for connectivity-sensitive work
- the generated target already follows the current transport preference from
  [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
- `clusterctl deploy` is the preferred wrapper when you want that same tool
  with candidate resolution printed first

## Colmena

Run:

```bash
nix run .#colmena -- apply --on r640-0
```

Use it for:

- routine fleet rollout
- fan-out deploys across several hosts
- pushing trust-graph changes after multiple identities were enrolled

Why:

- it is convenient for broad stateless rollout
- it pairs well with a stable Ygg transport once enrollment is complete

If you are not specifically choosing Colmena for fast fan-out, prefer
`clusterctl deploy` so the resolved target selection is visible in the output.

## Transport Model

The generated deployment targets now resolve like this:

1. active Ygg deploy host from materialized registry state
2. staged Ygg deploy host from materialized registry state
3. deprecated Ygg deploy host from materialized registry state
4. bootstrap `targetHost`
5. plain host name

That lets a host begin life on a raw management IP and later switch to Ygg
without rewriting the deployment generators by hand.

For the full current `clusterctl` command surface, including `registry`,
`identity`, `bundle`, `receipt`, and `host-age`, see
[`reference/clusterctl.md`](./reference/clusterctl.md).
