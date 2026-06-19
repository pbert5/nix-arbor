# Live Cluster Identity Registry Status

This directory is no longer the operator-facing registry plan. Current registry
truth lives in:

- [`docs/cluster-ops/identity/registry/`](../../docs/cluster-ops/identity/registry/)
- [`docs/cluster-ops/identity/operations/`](../../docs/cluster-ops/identity/operations/)
- [`dendrites/system/dendrites/cluster-identity/README.md`](../../dendrites/system/dendrites/cluster-identity/README.md)

Older design notes were moved under [`deprecated/`](./deprecated/). Treat them
as historical context only. When behavior changes, update the docs above and the
cluster-identity dendrite docs, not the deprecated notes.

## Current Repo State

The current implementation keeps durable identity truth in the flake and mirrors
fast-changing public facts plus private-delivery metadata into the live
registry.

Current source and policy surfaces:

- `inventory/identities.nix`
- `inventory/keys/host-age-recipients.nix`
- `inventory/keys/identities/cluster-private-identities.sops.yaml`
- `inventory/keys/followers/host-age-private-keys.sops.yaml`
- `inventory/identity-policy.nix`
- `.sops.yaml`
- `dendrites/system/dendrites/cluster-identity/cluster-identity.nix`
- `tools/clusterctl/clusterctl/`

Implemented command surfaces:

- `clusterctl registry init|validate|reconcile|materialize|sync|push|notify|status`
- `clusterctl identity publish|publish-public|publish-inventory|promote|burn|status|apply`
- `clusterctl bundle publish`
- `clusterctl receipt write|collect`
- `clusterctl deploy HOST --dry-run`

Implemented runtime behavior:

- leaders can publish the flake identity ledger with `clusterctl identity publish`
- leaders run best-effort publish during activation when enabled
- followers fetch, validate, reconcile, and materialize on a systemd timer
- registry state materializes under `/run/cluster-identity`
- SSH known-host, Yggdrasil, Radicle, and git-annex views are generated for
  consumers
- private blocks in `inventory/identities.nix` become registry
  `privateDelivery` metadata, not plaintext private keys
- receipt gating, burn records, duplicate detection, and timestamp-aware
  reconciliation are present
- `dev-machine` and `compute-worker` identity inventory has been moved out of
  active inventory into `inventory/deprecated/`

## Still Planned

These are current planned items, not implemented behavior:

- decryptability-aware follower selection that verifies decrypted plaintext
  hashes and derived public identities before activation
- service identity generation and rotation commands
- fully automated service identity delivery from decrypted SOPS ledger entries
- richer service-specific reload or restart policy after materialized state
  changes
