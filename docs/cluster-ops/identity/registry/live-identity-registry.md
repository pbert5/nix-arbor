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
- `inventory/identity-services/yggdrasil.nix`
- `inventory/identity-services/ssh-host.nix`
- `inventory/identity-services/radicle.nix`
- `inventory/identity-services/git-annex.nix`

`inventory/identities.nix` assembles those service-specific ledgers into the
published identity surface.

Private service identity material lives in
`inventory/keys/identities/cluster-private-identities.sops.yaml`, encrypted by
SOPS to leader host-age recipients from `.sops.yaml`. Public compatibility data
for the existing private Yggdrasil network is projected back through
`inventory/private-yggdrasil-identities.nix` into `inventory/networks.nix`.

Per-host age recipients live in
`inventory/keys/host-age-recipients.nix`. The private age key itself stays on
the host at `/var/lib/cluster-identity/age/host.agekey`; the flake records only
the public recipient and enrollment metadata. The leader-only recovery ledger
for those host age keypairs is
`inventory/keys/followers/host-age-private-keys.sops.yaml`. Enrolled recipients
are also projected as `host-age` identity records by `inventory/identities.nix`,
so the registry can mirror encryption-recipient state without carrying private
keys. Per-host private bundles should be encrypted to the target host
recipient.

The transport is not the trust layer. Git, Radicle, SSH, and fallback paths
only move data. Flake identity data, signed leader events, key-generation
timestamps, receipts, and burn records decide what is trusted.

Registry events, receipts, and encrypted bundle manifests are signed with
OpenSSH signatures in the `cluster-identity` namespace. The active policy
rejects placeholder signatures. Leader public keys and the local signing key
path are declared in `inventory/identity-policy.nix` and materialized into
`/etc/cluster-identity/policy.json`.

## Roles

Leaders write registry events, push remotes, and notify nodes to fetch.
Followers fetch the registry, validate events, reconcile state, and materialize
trusted runtime files under `/run/cluster-identity`.

Followers do not push to the registry in the MVP.

Leaders should also publish during normal activation. The
`system/cluster-identity` dendrite runs a best-effort
`clusterctl identity publish` on leader activation so regular rebuilds keep the
live projection close to the flake source ledger. Manual publish remains the
repair and debugging path.

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

For each `node/service`, the newest valid flake source timestamp wins inside
its state class. Freshly generated keys should use `keyGeneratedAt`; imported
legacy records can use `sourceTimestamp` as the point where the flake began
owning that identity. If an older legacy record does not carry a timestamp,
generation is used as a fallback ordering field. Burned fingerprints and burned
subject records override active, deprecated, and staged records.

## Promotion Rules

Active promotion uses the identity's timestamp from the flake identity source.
The registry event also has `createdAt`, but that is publish metadata, not the
identity age. Legacy records can still use monotonically increasing
`generation` until every flake identity source is timestamped.

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
material. In the SSH-only MVP, leaders can collect receipts over root SSH and
commit them to the registry.

## Commands

```bash
clusterctl registry init
clusterctl registry validate
clusterctl registry reconcile
clusterctl registry sync
clusterctl registry remotes sync
clusterctl identity generate-missing
clusterctl identity publish
clusterctl identity publish --service yggdrasil
clusterctl bundle seal r640-0 yggdrasil --generation 2 --source ./private.key --target-path /var/lib/yggdrasil/private.key --from-inventory
clusterctl host-age bootstrap r640-0
clusterctl identity promote r640-0 yggdrasil --generation 1
clusterctl identity burn r640-0 yggdrasil --generation 1 --fingerprint sha256:... --reason "suspected compromise"
```
