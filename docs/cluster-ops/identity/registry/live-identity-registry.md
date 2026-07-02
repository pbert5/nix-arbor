# Live Cluster Identity Registry

The live identity registry lets the cluster learn fast-changing identity facts
without a full flake rebuild. It is a live projection of flake-declared
identity truth, not an independent source of authority.

## What Stays In The Flake

- service capability flags and dendrite selection
- service modules and hardware config
- public and private identity source data
- leader policy and registry paths
- which machines are leaders
- fallback bootstrap paths from `inventory/host-bootstrap.nix`
- which services consume live identity data

## What Is Mirrored Into The Registry

- current Yggdrasil addresses
- SSH host public keys
- Radicle node IDs
- git-annex endpoint metadata
- deprecated fallback identities
- burned or compromised identities
- pending private identity deliveries
- receipts from target nodes

The registry can be rebuilt from the flake identity inventory. Leaders publish
flake-declared identity records into the registry with `clusterctl`, and
followers converge to the registry state at runtime.

Current public identity source data lives in:

- `inventory/keys/host-age-recipients.nix` for host age recipients
- `inventory/identity-services/ipns-publisher.nix` for leader IPNS names
- `inventory/identity-services/yggdrasil.nix`
- `inventory/identity-services/ssh-host.nix`
- `inventory/identity-services/radicle.nix`
- `inventory/identity-services/git-annex.nix`

`inventory/identity-services/identities.nix` assembles those service-specific
ledgers into the published identity surface.

Private service identity material lives in
`inventory/keys/identities/cluster-private-identities.sops.yaml`, encrypted by
SOPS to leader host-age recipients from `.sops.yaml`. Public compatibility data
for the existing private Yggdrasil network is projected from
`inventory/identity-services/yggdrasil.nix` into `inventory/networks.nix`.

Leader IPNS private publishing keys live separately in
`inventory/keys/leaders/leader-ipns-keys.sops.yaml`. They are generated from
the dendrite requirement surface with `clusterctl identity generate-missing`;
they are not generated during rebuild.

Per-host age recipients live in
`inventory/keys/host-age-recipients.nix`. The private age key itself stays on
the host at `/var/lib/cluster-identity/age/host.agekey`; the flake records only
the public recipient and enrollment metadata. The leader-only recovery ledger
for those host age keypairs is
`inventory/keys/followers/host-age-private-keys.sops.yaml`. Enrolled recipients
are also projected as `host-age` identity records by
`inventory/identity-services/identities.nix`,
so the registry can mirror encryption-recipient state without carrying private
keys. Per-host private bundles should be encrypted to the target host
recipient.

The transport is not the trust layer. IPFS, IPNS, PubSub, transitional Git,
and fallback paths only move or locate data. Trusted leader signatures,
authorization policy, monotonic generations, hash chains, receipts, burn
records, decryptability checks, and local anti-rollback state decide what is
trusted.

Registry events, receipts, and encrypted bundle manifests are signed with
OpenSSH signatures in the `cluster-identity` namespace. The active policy
rejects placeholder signatures. Leader public keys and the local signing key
path are declared in `inventory/identity-policy.nix` and materialized into
`/etc/cluster-identity/policy.json`.

## Roles

Leaders write registry events and publish immutable snapshots. Followers
resolve trusted IPNS heads, fetch through IPFS, validate events, reconcile
state, pin accepted CIDs, and materialize trusted runtime files under
`/run/cluster-identity`.

Followers do not push to the registry in the MVP.

All non-bootstrap registry participants also subscribe to the signed cluster
PubSub topic. A valid hint only starts the normal IPNS fetch path; it cannot
bypass trusted-name resolution, immutable snapshot verification, ancestry
checks, reconciliation, or anti-rollback state.

Only the leader acting for an explicit
deploy, identity publish, or administrator-requested registry mutation may
append to its registry history. Receiving, fetching, mirroring, or reconciling
another leader's state may update local caches and conflict views, but must not
trigger a new publication from the receiving leader.

`clusterctl deploy` publishes the deploying leader's flake identity ledger
after a successful deployment. Use `--no-publish-identities` for an explicit
exception. NixOS activation on the receiving host never publishes the ledger,
so a missing or stale target-side checkout cannot become fresh registry
history.

## Event States

Valid states are:

```text
planned
staged
private-delivered
node-received
node-activated
leader-verified
active
deprecated
removed
burned
```

For each `node/service`, monotonic `generation` is the ordering field.
`keyGeneratedAt`, `sourceTimestamp`, and event `createdAt` are audit metadata,
not ordering inputs. Different payload hashes at the same generation freeze the
subject at its last-good generation. A unique higher generation repairs the
conflict. Burned fingerprints override every lifecycle state and cannot be
reintroduced.

Append-only supersedence can override the normal generation ordering with an
explicit signed resolution. It preserves both conflicting entries and appends
a new record selecting one exact existing entry over the other, including
across generation boundaries. See
[`append-only-supersedence.md`](./append-only-supersedence.md).

## Promotion Rules

Active promotion uses monotonic generation and a payload hash that remains
stable across lifecycle transitions. A staged and active event for the same
identity generation therefore agree; two different keys at that generation do
not.

Private-delivery events require target receipts before they are promoted to
active when `requireReceiptBeforePromote` is enabled. Public-only records such
as an SSH host key can be published active by a trusted leader.

When a flake identity record includes a `private` block, `clusterctl identity
publish` mirrors that block as registry `privateDelivery` metadata. It does not
copy the private key into the registry. Set `private.requiresReceipt = true`
only for a delivery that should block active promotion until the target writes
or returns a receipt.

Encrypted bundle delivery uses signed bundle manifests in `bundles/`.
`clusterctl bundle seal` encrypts a host-targeted bundle to the target host-age
recipient and signs a manifest with recipient, ciphertext, plaintext, and
expected-public metadata. Recipient fingerprints are only a fast prefilter; the
target must decrypt the bundle, verify the plaintext hash, and verify that the
private key derives the public identity in the registry event before applying
it.

## Burn Rules

Burn records are intentionally blunt. If a key or identity is suspected
compromised, publish a `burned` event with the fingerprint and reason, then
push and notify. Burned records override later attempts to reintroduce the same
fingerprint.

## Receipt Rules

Receipts are written by target nodes after they receive or activate private
material. Receipts must be signed by a registered SSH host key for that node.
During the transport migration, leaders can still collect receipts over root
SSH and place them in the registry working directory.

## Canonical Content And Local State

The normative record format, hash and signature preimages, IPFS directory
shape, and conflict rules are defined in
[`registry-content-v1.md`](./registry-content-v1.md).

Every node persists checkpoints and last-good state under
`/var/lib/cluster-identity/local-state`. This state is outside fetched
snapshots, so serving an older but valid snapshot cannot roll the node back.

The materialized SSH view has two files:

- `/run/cluster-identity/ssh_config` maps each normal host name and its
  `HOST-ygg` alias to the active registry Yggdrasil endpoint.
- `/run/cluster-identity/ssh_known_hosts` contains the active SSH host keys.

The system SSH client and Home Manager include the live config before their
declarative fallback blocks. Normal host aliases therefore follow registry
changes immediately for root and regular users. User-local authentication keys
come from `users.<name>.org.ssh.identityFiles` and are offered only when the
file exists on the current machine. The explicit `HOST-bootstrap` aliases
retain the inventory bootstrap address and any explicitly declared bootstrap
identity file for recovery.

## Commands

```bash
clusterctl registry validate
clusterctl registry reconcile
clusterctl registry snapshot --publisher "$(hostname)"
clusterctl registry publish-ipfs --publisher "$(hostname)"
clusterctl registry fetch-ipfs
systemctl status cluster-identity-pubsub-listener.service
clusterctl identity generate-missing
clusterctl identity publish
clusterctl identity publish --service yggdrasil
clusterctl identity resolve --winner-event sha256:... --loser-event sha256:... --reason "manual resolution"
clusterctl bundle seal r640-0 yggdrasil --generation 2 --source ./private.key --target-path /var/lib/yggdrasil/private.key --from-inventory
clusterctl host-age bootstrap r640-0
clusterctl identity promote r640-0 yggdrasil --generation 1
clusterctl identity burn r640-0 yggdrasil --generation 1 --fingerprint sha256:... --reason "suspected compromise"
```

`clusterctl registry listen-pubsub` is an internal command owned by the
declarative systemd listener. The existing `clusterctl registry notify`
command remains an SSH-triggered migration and repair fallback.
