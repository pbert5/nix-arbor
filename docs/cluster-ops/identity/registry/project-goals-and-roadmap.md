# Registry Goals And Roadmap

The cluster identity registry lets a freshly enrolled node discover and verify
the current public and private identity material needed to join the cluster.
The node starts with only trusted leader signing keys, trusted leader IPNS
names, optional onion mirrors, and its own host age private key.

## Project Goals

- Publish immutable, content-addressed registry snapshots and encrypted bundles.
- Give each leader a stable IPNS head without treating IPNS as an authority.
- Make every trust decision locally from signatures, authorization policy,
  generations, event chains, burns, receipts, decryptability, and checkpoints.
- Preserve last-good state through outages, stale peers, rollback attempts, and
  same-generation leader conflicts.
- Keep leader and node behavior declarative in NixOS modules and inventory.
- Let PubSub, Tor mirrors, and future pin coordination improve discovery and
  availability without changing the acceptance rules.

## Non-Goals

- IPFS consensus or using the IPFS network as a source of truth.
- Accepting the newest IPNS answer without cryptographic verification.
- Requiring PubSub for convergence.
- Storing unencrypted service private keys in snapshots or the Nix store.
- Silently choosing between different payloads at the same generation.

## Delivery Phases

### Phase 1: Content And Verification

Implemented. Canonical JSON records, OpenSSH signatures, per-leader hash
chains, bundle manifests, receipts, burn precedence, conflict freezing,
quorum hooks, and persistent anti-rollback state are present.

### Phase 2: IPFS And IPNS Publication

Implemented in code. Leaders build an exhaustive signed snapshot, add and pin
it through Kubo, preserve a monotonic root sequence and previous CID, and
publish the accepted CID through an enrolled IPNS key. The NixOS dendrite owns
Kubo, key import, publication timers, and a best-effort rebuild trigger.

Live leader enrollment is intentionally separate. The
`system/cluster-identity` dendrite declares the per-leader `ipns-publisher`
requirement, and `clusterctl identity generate-missing` creates the public
inventory record plus SOPS-encrypted private ledger before publisher units are
enabled.

### Phase 3: Follower Convergence

Implemented. Followers resolve every enrolled trusted IPNS head, cache and
verify candidate roots, enforce per-leader root sequence and ancestry, assemble
only each publisher's own signed event chain, reconcile all accepted views,
update anti-rollback checkpoints, materialize local state, and recursively pin
accepted CIDs. Failed, stale, or equivocating heads retain last-good state.

Live-cluster validated on June 23, 2026: `t320-0` accepted root sequence 2 from
both `desktoptoodle` and `r640-0`, pinned both immutable roots, materialized the
combined state, and reported an empty conflict set.

Git/SSH and Radicle registry fetch are disabled in the default inventory. They
remain available only as explicit code-level migration transports.

### Phase 4: PubSub Hints

Implemented in code. After a successful IPFS/IPNS publication, leaders emit a
signed announcement containing the cluster, topic, leader, trusted IPNS name,
root CID, root sequence, previous CID, root digest, and creation time.
Followers verify the leader signature, policy bindings, timestamp window, and
message shape before starting the normal Phase 3 fetch service.

Announcements never install the hinted CID directly. Followers still resolve
trusted IPNS names and apply all Phase 3 verification, ancestry, conflict, and
anti-rollback checks. Timed IPNS polling remains the convergence mechanism.

MicroVM validated on June 23, 2026: two independent Kubo nodes exchanged a
real signed announcement, the listener accepted it, and the configured systemd
fetch unit was triggered. Live-cluster rollout and validation remain pending.

### Phase B1: Per-Node Implementation Status Via IPNS (Alternative Bonus Path)

Implemented in code. Every registry participant now declares a `status-ipns`
identity requirement. A leader can enroll it with:

```bash
nix run .#clusterctl -- identity generate-missing --service status-ipns &&
nix run .#clusterctl -- identity publish --service status-ipns
```

The generator creates or reuses a node-local Kubo IPNS key named
`cluster-identity-status-HOST` over the existing leader SSH path and records
only the public IPNS name in `inventory/identity-services/status-ipns.nix`.
The private status IPNS key stays in the node's local Kubo keystore by default;
leaders designate and distribute the public binding through the registry. This
is the preferred B1 model because status publication is node-local custody, not
a leader-held follower private-key ledger. If node-local enrollment fails for a
leader host, `clusterctl` can fall back to a leader-generated SOPS-backed IPNS
key in the existing private identity ledger; the target leader imports that key
during deployment before publishing status. Followers do not use this fallback
because the current private identity ledger is leader-encrypted.

Once a node has an enrolled public status IPNS name and has been rebuilt, the
`cluster-identity-status-publish.timer` publishes a signed `status.json`
directory through IPFS/IPNS. The record is signed with the node SSH host key and
contains the active, staged, deprecated, burned, conflict, and accepted-head
view materialized under `/run/cluster-identity`.

This gives the cluster a cheap, decentralized status/discovery board layered on
top of the existing trust model. It does not change acceptance rules from
Phases 1-4; it only advertises a signed view of what each node has actually
converged on for operational visibility.

### Phase 5: Onion Mirrors

Implemented in code. An enrolled leader onion service exposes a signed
per-leader head plus immutable snapshots keyed by CID. Followers use the onion
head only when trusted IPNS resolution fails, or use the onion snapshot path
when IPFS retrieval fails. The signed head binds the leader, configured onion
address, CID, root sequence, ancestry, and canonical root digest.

Onion retrieval feeds the normal Phase 3 verifier and reconciliation path.
It does not bypass signatures, exhaustive content hashes, ancestry,
anti-rollback checkpoints, conflict freezing, or last-good retention. Tor
service keys require separate live enrollment before the optional mirror is
activated on a leader. Enrollment records the Tor v3 public service key and
derives the trusted onion URL from that key.

### Phase 6: Pin Coordination

Planned and optional. IPFS Cluster CRDT coordination may replicate accepted
roots and bundles. It will not participate in trust decisions.

### Phase 7: Append-Only Conflict Resolution

Implemented. Conflicts are resolved by appending signed supersedence records,
not by editing immutable entries. An administrator can choose an existing
entry on any leader, and a leader creating a new entry can explicitly
supersede a conflict that was already visible when it published.

Supersedence may select a lower-generation entry over a faulty
higher-generation entry, but it must reference the exact existing target by
hash and embed the signed target as an existence proof. The accepted immutable
root CID is also recorded when known. Unknown, guessed, wildcard, and future
targets are invalid.

Leaders append registry history only for an explicit deploy, identity
publish, or administrator-requested registry mutation. Receiving or
reconciling another leader's state may update caches and conflict views but
must not trigger a publication. The detailed design is in
[`append-only-supersedence.md`](./append-only-supersedence.md).

## Completion Criteria

The redesign is complete when a fresh follower can boot with the four-item
bootstrap seed, resolve multiple leader heads, reject stale or conflicting
content, decrypt only its bundles, persist accepted state across reboot, and
materialize all supported service identities without Git transport.
