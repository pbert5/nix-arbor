# Deployment Tools

After a host is enrolled, normal operations should use the flake-generated
deployment surfaces and flake-pinned tool binaries.

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

## Transport Model

The generated deployment targets now resolve like this:

1. explicit `org.deployment.targetHost`
2. enrolled Ygg address if the host bootstrap metadata says
   `deploymentTransport = "privateYggdrasil"`
3. bootstrap `targetHost`
4. inventory node endpoint fallbacks

That lets a host begin life on a raw management IP and later switch to Ygg
without rewriting the deployment generators by hand.
