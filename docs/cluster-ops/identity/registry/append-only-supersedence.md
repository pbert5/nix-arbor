# Append-Only Registry Supersedence

This document specifies the implemented conflict-resolution extension to
registry v1.

## Goal

Resolving a conflict must not edit or delete a published registry entry.
Resolution appends a signed supersedence record that identifies one concrete
entry as superseding another:

```text
leader-a:13 = payload R13a
leader-b:13 = payload R13b

resolution:
  superseding entry = leader-b:13
  superseded entry = leader-a:13
```

Both original entries remain immutable and fetchable. The resolution record is
new registry history. Signed snapshot roots publish the leader's event-chain
tip, and followers reject descendant roots that truncate or fork any previously
accepted record.

## Resolution Policy

When conflicting entries have no valid supersedence relation, the resolver
freezes the affected `node/service` at its persisted last-good state and
reports the conflict.

An authorized administrator, currently Ash, can run a resolution command on
any leader, choose the correct entry, and append a signed supersedence record.
The command does not rewrite either original entry.

A leader creating a new registry entry may append a supersedence record in the
same registry-changing operation when it already sees a conflicting entry and
intentionally chooses its new entry. Merely fetching, mirroring, or observing a
conflict must not create a supersedence record.

## Existing-Entry Requirement

**A supersedence record can supersede only a concrete existing registry entry,
identified by cryptographic hash; it cannot target a future or guessed
entry.**

The record must bind at least:

- the superseding entry's event hash, leader, subject, and generation
- the superseded entry's event hash, leader, subject, and generation
- embedded signed copies of both exact identity events as existence proofs
- the accepted immutable root CID containing the superseded entry when known
- the resolution reason and signer
- the supersedence record's signature

The resolver accepts the record only when it can verify both embedded events,
their hashes and signatures, and their shared `node/service` subject. A
resolution found through an accepted follower view also records the known root
CID for auditability.

A wildcard, missing, unknown, or merely predicted target is invalid. A
resolution such as “supersede whatever leader B publishes next” is therefore
impossible. Embedding the signed target also lets one leader publish a
resolution without copying or altering the other leader's event chain.

## Generation Is Not Absolute Authority

Supersedence may cross generation boundaries. An authorized resolution can
select a lower-generation entry over an existing higher-generation entry:

```text
leader-a:13 supersedes leader-b:999
```

Generation remains the normal monotonic ordering mechanism, but an
artificially large generation cannot permanently lock out a correct entry.
The resolution record must still reference the exact higher-generation entry;
it cannot reserve authority over unseen future generations.

## Resolver Behavior

For each `node/service`, the resolver:

1. Verifies entry signatures, leader chains, payload hashes, burns, receipts,
   and local anti-rollback state.
2. Verifies supersedence signatures and authorization.
3. Rejects supersedence records whose embedded signed entries or exact hash
   references are absent or invalid.
4. Builds the normally highest relevant candidate set, also retaining any
   lower-generation entry that validly supersedes a higher candidate.
5. Removes exact candidates superseded by valid records, regardless of
   generation.
6. Accepts the result when exactly one maximal unsuperseded claim remains.
7. Freezes at last-good and reports the conflict when multiple maximal claims
   remain or the supersedence graph is ambiguous or cyclic.

Burn rules remain independent and stronger: a supersedence record cannot make
a burned fingerprint eligible again.

## Leader Write Discipline

A leader may append to its registry history only as part of an explicit
deploy, identity publish, or administrator-requested registry mutation for
which that leader is the actor.

Receiving another leader's registry may update the local cache, conflict view,
and resolver output. It must not cause the receiving leader to append or
republish registry history. In particular:

```text
receive, fetch, or mirror:
  cache and reconcile only

deploy, publish, or explicit resolve:
  may append an entry and valid supersedence records
```

This boundary prevents a leader from turning received state or stale local
flake configuration into a fresh authoritative publication.

## Commands

Resolve a reported conflict by copying the exact event hashes from
`conflicts.json`. For a deliberate lower-over-higher correction, use the
checkpointed/active event hash and the desired historical event hash:

```bash
clusterctl identity resolve \
  --winner-event sha256:... \
  --loser-event sha256:... \
  --reason "manual resolution"
```

The command signs and appends the supersedence record, reconciles local state,
and publishes a new IPFS/IPNS root when that transport is enabled. Normal
`clusterctl identity publish` operations automatically append supersedence
records when their new entry intentionally conflicts with an already observed
entry from another leader at the same or a higher generation.
