# Planned Registry Contract

Status: planned. Schema names and fields remain proposals until implementation.

## Design Constraint

Identity state remains represented by the existing identity events:
`staged`, `active`, `deprecated`, and `burned`. Rotation coordination is
separate metadata. It must not introduce an identity state that is
simultaneously trusted and supposedly burned.

## Rotation Intent

Append a leader-signed record to the leader event chain:

```json
{
  "schema": "cluster.identity.rotation.v1",
  "clusterId": "cluster-name",
  "rotationId": "rotation-...",
  "eventId": "rotation-...",
  "leader": "leader-a",
  "leaderKeyId": "SHA256:...",
  "policyGeneration": 1,
  "mode": "graceful",
  "reason": "guest access removed",
  "trigger": {
    "kind": "access-removed",
    "hosts": ["follower-a"],
    "principals": ["guest-name"]
  },
  "targets": [
    {
      "node": "follower-a",
      "service": "yggdrasil",
      "generation": 2,
      "eventHash": "sha256:...",
      "fingerprint": "sha256:...",
      "exposureReason": "private key installed on exposed host"
    }
  ],
  "acknowledgementPolicy": {
    "minimum": 1,
    "requiredNodes": ["leader-a"],
    "deadline": "2026-07-07T00:00:00Z"
  },
  "transportOrder": [],
  "createdAt": "2026-06-30T00:00:00Z",
  "leaderSeq": 4,
  "previousLeaderEventHash": "sha256:...",
  "eventHash": "sha256:...",
  "signature": {}
}
```

Required validation:

- the signing leader is authorized by local policy;
- every exact target event exists and its hash, generation, subject, and
  fingerprint match;
- a target cannot name a future or guessed identity event;
- mode is `graceful` or `emergency`;
- emergency intents cannot use acknowledgements to postpone a burn;
- deadlines and thresholds are bounded by local policy;
- transport order never schedules all trusted transports unavailable at once.

Like supersedence, exact embedded identity-event evidence may be used when the
record must remain independently verifiable after aggregation.

## Progress Evidence

Do not mutate the rotation intent. Derive progress from append-only evidence:

- a higher-generation staged or active identity event proves replacement
  publication;
- existing private-delivery receipts prove installation where applicable;
- a new signed rotation acknowledgement proves a node has accepted the new
  public identity or transport route;
- a deprecated identity event proves graceful retirement began;
- an existing burned identity event proves final invalidation;
- a provider-revocation note records external revocation that the registry
  cannot verify cryptographically.

Proposed acknowledgement:

```json
{
  "schema": "cluster.identity.rotation-ack.v1",
  "clusterId": "cluster-name",
  "rotationId": "rotation-...",
  "node": "follower-a",
  "replacementEventHashes": ["sha256:..."],
  "acceptedRootCid": "bafy...",
  "acceptedAt": "2026-06-30T00:10:00Z",
  "keyId": "SHA256:...",
  "signature": {}
}
```

The acknowledgement key must already be trusted for that node by local policy
or by its active SSH-host identity. An acknowledgement is evidence of adoption,
not authority to choose a winner or authorize a burn.

## Derived Rotation View

Materialization should add `rotations.json` without changing existing
`active.json`, `staged.json`, `deprecated.json`, or `burned.json`.

Each rotation derives one of:

- `requested`
- `replacement-pending`
- `awaiting-acknowledgements`
- `ready-to-retire`
- `deprecated`
- `complete`
- `emergency-incomplete`
- `blocked`
- `cancelled`

The derived view includes per-target evidence, missing acknowledgements,
deadline state, exclusions, and the next safe operator command.

Cancellation is append-only and is allowed only before any emergency burn. It
does not undo already published identity events, external revocations, or
burns.

## Transport Handoff Invariants

For graceful IPNS/onion rotation:

1. Generate the replacement transport key.
2. Add the replacement route to trusted policy using the required policy
   authorization.
3. Publish the same or newer signed root through both old and new routes.
4. Collect acknowledgements through signed node status or rotation receipts.
5. Retire the old primary only while another route remains trusted and live.
6. Rotate the next route after the first handoff reaches its policy threshold.
7. Burn or revoke the old transport key.

The old route may advertise the replacement while it remains trusted. Once its
key is suspected compromised, it is not valid evidence for authorizing the
replacement.

## Anti-Lockout Rules

- Rotation intent targets must name already observed event hashes.
- Replacement generations are generated from current reconciled state, not
  arbitrary user-supplied giant generation numbers.
- A transport rotation cannot remove the final usable trusted route in
  graceful mode.
- Emergency mode may sacrifice availability, but prints and records the
  required recovery path.
- Acknowledgement thresholds are evaluated against the declared eligible set,
  with exclusions explicit and signed.
- Followers that miss a completed transport rotation require bootstrap or
  re-enrollment; they do not force old compromised keys back into service.

## Snapshot And Aggregation Changes

Planned content handling:

- include rotation intents in immutable snapshot content and leader hash-chain
  tips;
- include rotation acknowledgements alongside receipts;
- copy both through follower aggregation;
- validate hashes and signatures before deriving `rotations.json`;
- include rotation summary in signed node status;
- preserve last-good rotation state on malformed or conflicting records.
