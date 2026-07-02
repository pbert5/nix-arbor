# Registry Content V1

Registry v1 is a directory of canonical JSON records suitable for an immutable
IPFS snapshot. Transport is not part of the trust decision.

## Directory Shape

```text
root.json
policy/leader-policy.json
events/<leader>/<12-digit-leader-sequence>.json
bundles/<node>/<service>/gen-<generation>.age
bundles/<node>/<service>/gen-<generation>.manifest.json
receipts/<node>/<service>-gen-<generation>.receipt.json
state/active.json
state/staged.json
state/deprecated.json
state/burned.json
state/conflicts.json
```

`events/`, `bundles/`, `receipts/`, and `policy/` are source material.
`state/` is a generated cache and is never authoritative.

## Canonical JSON Profile

Signed and hashed records use the registry's integer-only RFC 8785-compatible
profile:

- UTF-8 JSON
- object keys sorted lexicographically
- no insignificant whitespace
- NFC-normalized strings
- integers, booleans, strings, null, arrays, and objects only
- no floating-point values or duplicate object keys

Files end in one LF byte. The LF is included in file digests listed by
`root.json`; it is not included in canonical record hashes or signature
preimages.

## Hash And Signature Preimages

- A record signature covers canonical JSON after removing top-level
  `signature` and `signatures`.
- `eventHash` is SHA-256 of canonical JSON after removing top-level
  `eventHash`, `signature`, and `signatures`.
- `payloadHash` is SHA-256 of `clusterId`, `subject`, `generation`, `public`,
  `privateDelivery`, and `burned`, omitting absent fields.
- SHA-256 values use `sha256:<lowercase-hex>`.
- Public identity fingerprints are SHA-256 of the UTF-8 public key, recipient,
  node ID, or endpoint string selected for that service. Writers embed the
  result in `public.fingerprint`; verifiers derive it again before burn checks.
- OpenSSH signatures use namespace `cluster-identity` and carry the signing
  key's `SHA256:...` fingerprint as `keyId`.

`state`, lifecycle timestamps, leader metadata, and supersession links are not
part of `payloadHash`. A staged event and its later active promotion therefore
have the same payload hash. A different key or delivery at the same generation
does not.

## Identity Event Contract

Every identity event has schema `cluster.identity.event.v1` and includes:

```json
{
  "clusterId": "user1-homelab",
  "eventHash": "sha256:...",
  "eventId": "identity-...",
  "generation": 12,
  "leader": "desktoptoodle",
  "leaderKeyId": "SHA256:...",
  "leaderSeq": 41,
  "payloadHash": "sha256:...",
  "previousLeaderEventHash": "sha256:...",
  "schema": "cluster.identity.event.v1",
  "state": "staged",
  "subject": {"node": "r640-0", "service": "yggdrasil"}
}
```

The first event for a leader has sequence 1 and a null previous hash. Sequence
numbers are contiguous. Each later event names the prior event hash.

Burns are events with state `burned` and a `burned` object containing
`fingerprint`, `reason`, `burnedAt`, and `scope`. A burned fingerprint is never
eligible again, regardless of generation or transport source.

## Supersedence Contract

Supersedence records use schema `cluster.identity.supersedence.v1` and occupy
the same contiguous per-leader event chain. Each record contains:

- the common leader sequence, previous hash, event hash, and signature fields
- the shared `node/service` subject
- `superseding` and `superseded` references containing exact event hashes,
  leaders, and generations
- `supersedingEvent` and `supersededEvent`, which embed both signed identity
  events as existence proofs
- `observedRootCid` when the superseded event came from a known accepted root
- a non-empty resolution reason

Both embedded events must have valid identity payload hashes, event hashes, and
trusted leader signatures. They must conflict and name the same subject.
Consequently, a resolution cannot target an unknown wildcard or future event.

## Root Contract

`root.json` has schema `cluster.identity.root.v1`. It identifies the cluster,
publisher, publisher key ID, monotonic `rootSequence`, previous root CID,
creation time, the publisher's `eventChainTip`, and every source object by
relative path and SHA-256 file digest. It is signed by the publisher.

The manifest is exhaustive. Files under `policy/`, `events/`, `bundles/`,
`receipts/`, or `state/` that are not listed make the snapshot invalid, as do
listed paths outside those source directories. This prevents an implementation
from ignoring an extra validly signed event that was not committed by the root.

IPNS only locates a candidate root. Acceptance still requires the root
signature, matching cluster ID, nondecreasing sequence, valid object digests,
valid event chains, and successful reconciliation.

The publisher increments `rootSequence` from persistent local publisher state.
`previousRootCid` is null for the first publication and the prior successfully
published CID thereafter. Failed IPFS or IPNS operations do not advance this
state. Followers also require every newer root to retain the previously
accepted publisher event-chain hash at its original sequence. A descendant
root therefore cannot truncate a supersedence record or any other accepted
leader history.

## Policy Contract

`policy/leader-policy.json` has schema `cluster.identity.policy.v1` and carries
`policyGeneration`, leaders, thresholds, rules, and a threshold OpenSSH
signature envelope. Updates are checked against the already trusted policy;
keys introduced by the candidate policy cannot authorize that same update.

The current bootstrap policy requires two leaders for policy updates and host
age rotation. Public service updates, private service rotation, and service
key burns require one leader.

## Bundle And Receipt Contracts

Bundle manifests use schema `cluster.identity.bundle.v1`. They bind the
subject and generation to an age recipient, ciphertext path and digest,
plaintext digest, target path, expected public identity, leader key ID, and
leader signature. The `.age` ciphertext is opaque.

Receipts use schema `cluster.identity.receipt.v1`. They bind a node, service,
generation, source event, bundle manifest, observed public identity, status,
and activation result. A receipt is accepted only when its OpenSSH signature
matches a registered active `ssh-host` key for that node.

Decryptability alone is not activation. The target must also verify the
plaintext digest and derive the expected public identity from the private
material. Those service-specific derivation checks remain planned work.

## Reconciliation

For each `node/service`:

1. A valid burn removes the subject and permanently records its fingerprint.
2. Valid supersedence records remove only their exact superseded event from the
   candidate set, regardless of generation.
3. Cyclic supersedence freezes the subject at last-good state.
4. Normal generation ordering runs over the remaining candidates.
5. Different payload hashes at the same highest remaining generation freeze
   the subject.
6. A generation below the local checkpoint is rejected unless its event
   validly supersedes the checkpointed event.
7. Host age rotation requires the configured leader threshold.
8. Receipt-gated private delivery remains staged until a valid receipt exists.

The detailed model and operator command are in
[`append-only-supersedence.md`](./append-only-supersedence.md).

Persistent state lives under `/var/lib/cluster-identity/local-state/`:

```text
checkpoint.json
fetch-status.json
last-good/active.json
last-good/staged.json
last-good/deprecated.json
last-good/burned.json
```

Materialized consumers include:

- `/run/cluster-identity/conflicts.json`
- `/run/cluster-identity/ssh_config`
- `/run/cluster-identity/ssh_known_hosts`
- `/run/cluster-identity/yggdrasil/peers.json`
- `/run/cluster-identity/radicle/nodes.json`
- `/run/cluster-identity/git-annex/remotes.json`

`checkpoint.json` also records `heads.<leader>` with the trusted IPNS name,
accepted CID, root sequence, and prior CID; `acceptedCids`; and
`highestRegistryCheckpointSeen`. Subject generations and leader heads are
updated only after candidate verification and successful reconciliation.

`fetch-status.json` is operational evidence, not authority. It records the
latest resolution result for each leader, including rejected rollback or
equivocation and any retained last-good CID.
