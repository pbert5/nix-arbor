# Bootstrap State Machine

This page describes the intended lifecycle of a host from first contact to
normal Ygg-based operation.

## States

### `raw-target`

The host is reachable somehow, but the repo does not yet treat it as an
enrolled cluster node.

Typical properties:

- reachable by IP or Tailscale
- root SSH may or may not already work
- Ygg identity may not exist yet
- no recorded public Ygg identity in inventory

### `bootstrap-reachable`

The host is reachable over SSH from a trusted leader using the intended
bootstrap identity.

Evidence:

- `ssh -i /path/to/key root@target 'hostname && whoami'` works

### `identity-known`

The host has a persistent Ygg private key and the operator can read back the
corresponding public identity.

Evidence:

- `bootstrap-host --dry-run` returns a public key and Ygg IPv6 address

### `inventory-enrolled`

The public identity and operator transport metadata have been written into the
repo.

Evidence:

- the host appears in
  [`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
- the host has current bootstrap/deploy metadata in
  [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)

### `deployed-over-bootstrap`

The host has received a real deployment, but normal deploy transport may still
point at a bootstrap IP or Tailscale endpoint.

Use this when:

- identity exists but you do not want to switch deployment to Ygg yet
- you are staging the trust graph gradually

### `deployed-over-ygg`

The host's generated deployment target now prefers the enrolled private Ygg
address.

Evidence:

- `nix eval '.#deploy.nodes.<host>' --json` shows the Ygg address as hostname

### `strict-peer-only`

The host has enough enrolled peer metadata to optionally enforce the stricter
"only explicit peers may contact this node over Ygg" posture.

Requirements:

- declared peers all have enrolled `publicKey`
- declared peers all have enrolled `address`
- relevant nodes have been redeployed with the updated trust graph

## State Transitions

Normal path:

1. `raw-target` -> `bootstrap-reachable`
2. `bootstrap-reachable` -> `identity-known`
3. `identity-known` -> `inventory-enrolled`
4. `inventory-enrolled` -> `deployed-over-bootstrap` or `deployed-over-ygg`
5. `deployed-over-ygg` -> `strict-peer-only`

## Tools Per Transition

- reachability check:
  `ssh -i /path/to/key root@target 'hostname && whoami'`
- identity discovery:
  `nix run .#bootstrap-host -- --host <host> --identity-file /path/to/key --dry-run`
- enrollment:
  `nix run .#bootstrap-host -- --host <host> --identity-file /path/to/key`
- first deployment:
  `nix run .#deploy-rs -- .#<host>` or `nix run .#colmena -- apply --on <host>`
- trust propagation:
  deploy the enrolled host and any peers that should trust it

## Failure Mode To Avoid

Do not confuse `identity-known` with `fully trusted fleet member`.

A host can have a perfectly valid Ygg identity and still not be fully trusted
by the rest of the fleet until those nodes receive updated configuration.
