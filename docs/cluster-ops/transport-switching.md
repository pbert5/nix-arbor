# Transport Switching

This guide explains how a host moves from bootstrap transport to Ygg transport.

## Bootstrap Transport

Use bootstrap transport when:

- a host has not been enrolled yet
- the Ygg identity is not trusted yet
- the generated deployment target should stay on a raw IP or Tailscale address

This is represented in `inventory/host-bootstrap.nix` as:

```nix
deploymentTransport = "bootstrap";
```

## Private Ygg Transport

Use Ygg transport when:

- the host has an enrolled Ygg public key
- the host has an enrolled Ygg address
- you want generated deploy targets to prefer the Ygg overlay

This is represented as:

```nix
deploymentTransport = "privateYggdrasil";
```

## What Actually Changes

The generated deploy surface starts preferring:

1. explicit deploy override
2. enrolled Ygg address
3. bootstrap target host
4. older fallbacks

You can inspect the current result with:

```bash
nix eval '.#deploy.nodes.r640-0' --json
```
