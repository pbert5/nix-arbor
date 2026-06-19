# Event And Reconciliation Model

## Trust Inputs

Trust comes from:

- flake-declared identity source records
- signed leader events
- trusted leader public keys from inventory policy
- identity `keyGeneratedAt` or `sourceTimestamp` timestamps
- monotonically increasing `generation` values as fallback ordering
- leader policy epoch
- receipts before promotion when required
- burned fingerprint and burned subject records

Event `createdAt` is publication metadata. It is not the age of the key.

## Identity Event Shape

Public identity event:

```json
{
  "schema": "cluster.identity.event.v1",
  "eventId": "EVENT_ID",
  "leader": "r640-0",
  "leaderKey": "ssh-ed25519 REPLACE_ME",
  "leaderPolicyEpoch": 1,
  "subject": {
    "node": "r640-0",
    "service": "yggdrasil"
  },
  "generation": 1,
  "state": "active",
  "public": {
    "sourceTimestamp": "2026-05-11T03:59:51Z",
    "yggdrasilPublicKey": "REPLACE_ME",
    "yggdrasilAddress": "REPLACE_ME",
    "deployHost": "REPLACE_ME"
  },
  "privateDelivery": null,
  "supersedes": [],
  "createdAt": "2026-05-11T04:30:00Z",
  "signature": "REPLACE_ME"
}
```

Private-delivery metadata event:

```json
{
  "schema": "cluster.identity.event.v1",
  "eventId": "EVENT_ID",
  "leader": "r640-0",
  "leaderKey": "ssh-ed25519 REPLACE_ME",
  "leaderPolicyEpoch": 1,
  "subject": {
    "node": "r640-0",
    "service": "yggdrasil"
  },
  "generation": 2,
  "state": "staged",
  "public": {
    "sourceTimestamp": "2026-05-11T05:00:00Z",
    "yggdrasilPublicKey": "REPLACE_ME",
    "yggdrasilAddress": "REPLACE_ME"
  },
  "privateDelivery": {
    "status": "planned",
    "recipientHost": "r640-0",
    "targetPath": "/var/lib/yggdrasil/private.key",
    "sopsPath": "identities.yggdrasil.r640-0.privateKey",
    "bundleManifest": "bundles/r640-0/yggdrasil/gen-2.manifest.json",
    "sourceTimestamp": "2026-05-11T05:00:00Z",
    "requiresReceipt": true
  },
  "supersedes": [],
  "createdAt": "2026-05-11T05:01:00Z",
  "signature": "REPLACE_ME"
}
```

The registry stores metadata or encrypted bundle material, not plaintext
private keys.

## Bundle Manifest Shape

Private bundle delivery should use a signed manifest. Recipient fingerprints
are a fast local prefilter, not the final proof of correctness.

```json
{
  "schema": "cluster.identity.bundle.v1",
  "subject": {
    "node": "r640-0",
    "service": "yggdrasil"
  },
  "generation": 2,
  "stateEventId": "identity-...",
  "targetPath": "/var/lib/yggdrasil/private.key",
  "encryption": {
    "method": "age-x25519",
    "recipientHost": "r640-0",
    "recipientPublicKey": "age1...",
    "recipientFingerprint": "sha256:...",
    "recipientSetDigest": "sha256:..."
  },
  "bundle": {
    "path": "bundles/r640-0/yggdrasil/gen-2.age",
    "ciphertextSha256": "sha256:...",
    "plaintextSha256": "sha256:..."
  },
  "expectedPublic": {
    "yggdrasilPublicKey": "...",
    "yggdrasilAddress": "..."
  },
  "createdAt": "2026-05-12T00:00:00Z",
  "leader": "r640-0",
  "signature": "..."
}
```

Receiver selection algorithm:

```text
For each host/service:
  1. Load candidate identity events from the registry.
  2. Reject invalid signatures, untrusted leaders, burned identities, and
     removed identities.
  3. Sort newest-first by keyGeneratedAt/sourceTimestamp, then generation.
  4. For each candidate:
       a. If it has no private material requirement, it is usable.
       b. If it has private delivery:
            i. Check whether the signed manifest says this host is an intended recipient.
           ii. If not, skip without trying decryption.
          iii. If yes, try decrypting the bundle with local host.agekey.
           iv. Verify decrypted content hash.
            v. Verify decrypted private key derives the public identity in the event.
           vi. If all pass, select it.
  5. If none decrypt, keep the last successfully applied private material.
```

`/run/cluster-identity/active.json` should eventually mean newest valid locally
usable active identity. A separate view such as
`/run/cluster-identity/registry-newest.json` can expose the newest leader
claim even when it is not locally usable.

## Burn Event Shape

Burn events use the same schema with `state = "burned"`:

```json
{
  "schema": "cluster.identity.event.v1",
  "eventId": "EVENT_ID",
  "leader": "r640-0",
  "leaderKey": "ssh-ed25519 REPLACE_ME",
  "leaderPolicyEpoch": 1,
  "subject": {
    "node": "r640-0",
    "service": "yggdrasil"
  },
  "generation": 2,
  "state": "burned",
  "burned": {
    "fingerprint": "sha256:REPLACE_ME",
    "reason": "suspected compromise"
  },
  "createdAt": "2026-05-11T05:10:00Z",
  "signature": "REPLACE_ME"
}
```

## Receipt Shape

Receipts use a separate schema:

```json
{
  "schema": "cluster.identity.receipt.v1",
  "node": "r640-0",
  "service": "yggdrasil",
  "generation": 2,
  "status": "node-activated",
  "activated": true,
  "observedPublic": {
    "yggdrasilAddress": "REPLACE_ME"
  },
  "signedByNode": "ssh-ed25519 REPLACE_ME",
  "createdAt": "2026-05-11T05:15:00Z",
  "signature": "REPLACE_ME"
}
```

## Valid States

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

Typical private identity lifecycle:

```text
planned
  -> staged
  -> private-delivered
  -> node-received
  -> node-activated
  -> leader-verified
  -> active
  -> deprecated
  -> removed
```

Compromise lifecycle:

```text
active
  -> burned
```

## Reconciliation Rules

Reconciliation reads all events and receipts, validates them, and computes
materialized state.

Rules:

- burned always wins
- removed records are ignored
- unsigned records are rejected
- leaders must be trusted for the current policy epoch
- active records are normal runtime truth
- staged records are visible to leaders and deploy tooling
- deprecated records are fallback-only
- newest valid identity timestamp wins for the same node/service/state class
- highest generation is fallback ordering when timestamp data is absent
- active private-delivery records require receipts when policy requires them
- a recipient should prefer a decryptable identity over a newer one it cannot
  decrypt
- recipient fingerprints are prefilters only; the decisive proof is decrypting
  the bundle, verifying the plaintext hash, and verifying that private material
  derives the public identity in the event

Outputs:

```text
state/active.json
state/staged.json
state/deprecated.json
state/burned.json
state/known_hosts
state/yggdrasil-peers.json
state/radicle-nodes.json
state/git-annex-remotes.json
```

Then materialization writes `/run/cluster-identity`.

## Current Implementation Notes

Implemented:

- event generation from `inventory/identities.nix`
- public timestamp propagation into registry event `public`
- private block propagation into registry `privateDelivery`
- duplicate suppression includes `privateDelivery`
- event ordering uses `keyGeneratedAt`, `sourceTimestamp`, then generation
- burned subject records suppress non-deprecated selected state

Planned:

- real SSH signature verification
- schema validation for service-specific public fields
- explicit decryptability-aware selection on followers
- signed bundle manifests and encrypted bundle lifecycle events
- local last-applied private material state
