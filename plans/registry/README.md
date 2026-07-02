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

- `inventory/identity-services/identities.nix`
- `inventory/identity-services/status-ipns.nix`
- `inventory/keys/host-age-recipients.nix`
- `inventory/keys/identities/cluster-private-identities.sops.yaml`
- `inventory/keys/followers/host-age-private-keys.sops.yaml`
- `inventory/identity-policy.nix`
- `.sops.yaml`
- `dendrites/system/dendrites/cluster-identity/cluster-identity.nix`
- `tools/clusterctl/clusterctl/`

Implemented command surfaces:

- `clusterctl registry init|validate|reconcile|materialize|snapshot|publish-ipfs|fetch-ipfs`
- `clusterctl registry listen-pubsub`
- `clusterctl registry ipns-key ensure`
- `clusterctl registry status-ipns-key ensure`
- `clusterctl registry publish-status`
- `clusterctl registry sync|push|notify|status`
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
- private blocks in `inventory/identity-services/identities.nix` become registry
  `privateDelivery` metadata, not plaintext private keys
- receipt gating, burn records, duplicate detection, and generation-first
  reconciliation are present
- canonical JSON signatures, per-leader event hash chains, generation-first
  conflict freezing, and persistent anti-rollback checkpoints are present
- leaders can build exhaustive signed snapshots, add and pin them with Kubo,
  publish monotonic heads through an enrolled IPNS key, and preserve the prior
  published CID
- the NixOS dendrite owns leader Kubo, SOPS-backed IPNS key import, publication
  timers, and best-effort rebuild publication triggers
- followers resolve all enrolled leader IPNS names, verify and cache immutable
  snapshots, reject rollback and root-chain forks, pin accepted CIDs, assemble
  leader-authored event chains, and materialize last-good state
- leaders publish signed PubSub root hints after successful IPFS/IPNS
  publication, and followers verify those hints before waking the normal fetch
  service
- every registry participant can enroll a node-local `status-ipns` identity;
  once enrolled and rebuilt, `cluster-identity-status-publish.timer` publishes a
  node-signed IPNS status document showing the services and identities actually
  materialized under `/run/cluster-identity`; leader hosts can fall back to a
  SOPS-backed status key when remote node-local enrollment is unavailable
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
- live leader IPNS key enrollment and rollout
- live rollout and validation of B1 node status IPNS publishing
- optional Tor onion mirrors and IPFS Cluster CRDT pin coordination

Signed PubSub root announcements are implemented in code. Live rollout and
validation remain pending; current behavior is documented under
`docs/cluster-ops/identity/registry/`.
