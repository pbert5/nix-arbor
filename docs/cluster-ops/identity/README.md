# Cluster Identity

This section covers live cluster identity data, registry transport, rollout
flows, and repair procedures.

The durable public source ledger is `inventory/identities.nix`. Private service
identity material is kept in
`inventory/keys/identities/cluster-private-identities.sops.yaml`, and host age
key recovery material is kept in
`inventory/keys/followers/host-age-private-keys.sops.yaml`. Both SOPS files are
encrypted to leader host-age recipients by `.sops.yaml`.

Per-host age recipients are declared in
`inventory/keys/host-age-recipients.nix`; private host age keys stay on the
hosts under `/var/lib/cluster-identity/age`.

The normal leader publish path is:

```bash
clusterctl identity matrix
clusterctl identity generate-missing
clusterctl identity publish
clusterctl identity smoke-test
```

Use `clusterctl identity matrix` first when you want a service-by-host view of
what identities should exist, which ones are missing from the flake source
ledgers, and which leader commands to run next for a focused repair or
rotation.

Use `clusterctl identity generate-missing` from a leader when you want the tool
to fill the auto-discoverable gaps directly into the declarative source files.
Today that covers host-age recipients, Yggdrasil public identity, SSH host
keys, Radicle node IDs, and derived git-annex endpoints. Generation runs as the
invoking user; its default publication phase automatically uses `sudo` when the
live registry or leader signing key is root-only.

Leader rebuilds also run a best-effort publish during activation through
`system/cluster-identity`. Use the explicit command for repair, debugging, and
immediate convergence after editing the ledger.

Use `clusterctl identity smoke-test` when you want a live IPFS/IPNS convergence
check. It publishes the current signed snapshot, triggers follower fetches,
then verifies that the selected hosts accepted the exact CID and root sequence.
It does not create synthetic identities.

## Registry

- [`registry/README.md`](/work/flake/docs/cluster-ops/identity/registry/README.md)
  is the starting point for the live registry system.
- [`registry/live-identity-registry.md`](/work/flake/docs/cluster-ops/identity/registry/live-identity-registry.md)
  explains what stays in the flake, what moves into the live registry, and how
  signed identity events become trusted runtime state.
- [`registry/identity-registry-transport.md`](/work/flake/docs/cluster-ops/identity/registry/identity-registry-transport.md)
  explains Git-over-SSH, Radicle, fallback SSH, follower timers, leader pushes,
  and notification behavior.

## Operations

- [`operations/README.md`](/work/flake/docs/cluster-ops/identity/operations/README.md)
  is the starting point for registry operator playbooks.
- [`operations/identity-rollout-playbook.md`](/work/flake/docs/cluster-ops/identity/operations/identity-rollout-playbook.md)
  gives step-by-step commands for initialization, publishing identities,
  private SSH delivery, burns, follower sync, and deploy dry runs.
- [`operations/identity-registry-troubleshooting.md`](/work/flake/docs/cluster-ops/identity/operations/identity-registry-troubleshooting.md)
  lists common registry, transport, materialization, and deploy-resolution
  failure modes with exact inspection commands.
