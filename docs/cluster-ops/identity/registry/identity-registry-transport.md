# Identity Registry Transport

The target registry transport is IPFS for immutable snapshots and encrypted
bundles, IPNS for stable leader-published heads, and PubSub for update hints.
None of these chooses trusted state; the local verifier does.

## Bootstrap Seed

A newly enrolled node receives declaratively through the flake:

- cluster ID
- trusted leader signing keys
- trusted leader IPNS names
- optional leader onion mirror addresses
- its own host age private key

Leader IPNS private publishing keys stay on leaders. Their public IPNS names
must be enrolled in inventory before IPNS publishing is enabled.

## Fetch Flow

For every trusted leader head, a follower:

1. resolve the configured IPNS name
2. fetch the immutable root directory from IPFS
3. verify `root.json` and every listed file digest
4. verify policy, event chains, bundles, and receipts
5. reconcile all valid leader views against local anti-rollback state
6. materialize only accepted state under `/run/cluster-identity`
7. pin accepted root and bundle CIDs

An unavailable or invalid leader head does not erase last-good state.

Fetched snapshots are cached under
`/var/lib/cluster-identity/follower-cache/<leader>/<cid>/`. The accepted working
view is assembled under `/var/lib/cluster-identity/accepted-registry/`; it is
separate from the writable leader registry. A publisher contributes its own
`events/<publisher>/` chain and its own signed bundle manifests. This prevents
one leader's root from choosing which events another leader authored.

For an already-known leader, a higher root must descend through contiguous
`rootSequence` and `previousRootCid` links to that leader's last accepted CID.
A lower sequence is rollback. A different CID at the same sequence is
equivocation. The root's `eventChainTip` must also retain the exact event hash
previously accepted at that sequence, preventing history truncation or forks.
All are rejected while the previous cached head remains active.

## Publishing Flow

After a successful `clusterctl deploy`, the deploying leader publishes flake
identity events from its source checkout. The Phase 2 publisher builds and
signs `root.json`, adds the directory to IPFS, pins its CID, and advances that
leader's IPNS name. Receiving-host activation and registry fetch never append
or publish leader history. Operators can also run `clusterctl identity publish`
as an explicit registry-changing operation.

During the first v1 activation, `clusterctl registry ensure-v1` archives an
incompatible pre-v1 working registry intact under a timestamped sibling path
and reseeds the active registry from flake truth.

Every leader keeps `/var/lib/cluster-identity/publisher-state/<leader>.json`.
It records the last published CID and sequence so the next root can increment
`rootSequence` and bind `previousRootCid`. The state is updated only after the
IPFS add, pin, and IPNS publish all succeed.

## PubSub

PubSub messages are signed hints containing cluster ID, leader, root CID, root
sequence, previous root CID, root digest, trusted IPNS name, topic binding, and
creation time. After a successful IPFS/IPNS publish, the leader sends the hint
on the inventory-declared cluster topic.

Every registry participant runs
`cluster-identity-pubsub-listener.service`. The listener rejects messages for
another cluster or topic, untrusted leaders, mismatched IPNS names, invalid or
stale timestamps, malformed CIDs or digests, and invalid signatures. A valid
hint starts `cluster-identity-fetch.service`; it never fetches or installs the
hinted CID directly. Hints for an already accepted head and older sequences are
ignored.

The listener records its last result and counters in
`/var/lib/cluster-identity/local-state/pubsub-status.json`. PubSub messages
never carry authoritative registry state and are not required for eventual
convergence. Subscription failures are retried in-process so Kubo restarts
during a NixOS switch do not turn a temporary transport gap into an activation
failure. The listener requests Kubo's newline-delimited JSON event encoding and
decodes the multibase message body before validating the signed announcement;
Kubo's raw subscription stream does not delimit consecutive messages.

## Optional Availability Layers

An enrolled Tor onion mirror exposes:

- `/heads/<leader>.json`, a signed head binding the configured onion address,
  CID, root sequence, previous CID, and canonical root digest
- `/ipfs/<cid>/`, the immutable signed snapshot and its exhaustive content
  index

Followers try the onion head only after trusted IPNS resolution fails and try
the onion snapshot after IPFS retrieval fails. Onion content enters the same
verification, ancestry, reconciliation, conflict, and anti-rollback path as
IPFS content. A Tor or mirror failure retains last-good state.

IPFS Cluster CRDT pin coordination may be added later for availability. It will
not change verification rules.

## Migration Status

Phases 1 through 5 are implemented in code. IPFS/IPNS leader publication is enabled only
after that leader has both an inventory `ipnsName` and a SOPS-backed publishing
key. This prevents an unequipped rebuild from inventing a new trust anchor.

Follower timers now use IPNS/IPFS and pin every accepted head. Git/SSH and
Radicle fetch are disabled by default. Signed PubSub hints wake the same fetch
path. Onion fallback is enabled in policy but remains inert until a leader has
an enrolled `onion-mirror` identity. IPFS Cluster remains planned.

### Onion Mirror Enrollment

For an optional leader mirror:

1. Set `org.clusterIdentity.onionMirrorService = true` on the leader and
   rebuild it once.
2. Run
   `clusterctl identity generate-missing --node <leader> --service onion-mirror`.
   The generator reads Tor's public service key and hostname from the leader,
   recomputes the v3 onion address from that public key, and rejects a
   mismatch.
3. Review the generated record in
   `inventory/identity-services/onion-mirror.nix`, then rebuild the cluster.

Tor retains the private service key under `/var/lib/tor`. The publisher
requires `cluster-identity-onion-address.service`, which checks that the
runtime hostname exactly matches the enrolled bootstrap address before signed
mirror heads can advance. The bootstrap policy includes both the derived onion
URL and the Tor v3 public service key.

The mirror is bounded as a single public ingress because Tor connects to Nginx
from loopback and hides the original client address. Inventory policy caps
aggregate concurrent requests, request rate and burst, per-connection
bandwidth, and Tor streams per rendezvous circuit. Nginx returns HTTP 429 when
its connection or request limits are exceeded and rejects methods other than
GET or HEAD.

### Live Rollout Status

Phase 3 was rolled out to `r640-0`, `desktoptoodle`, and `t320-0` on
June 23, 2026. Both leader IPNS heads reached root sequence 2. The follower
resolved and verified both heads, cached and recursively pinned both CIDs,
persisted both head checkpoints, materialized the accepted registry, and
reported no subject conflicts.

The rollout also exercised the declarative pre-v1 migration: each leader's
legacy writable registry was preserved under a timestamped
`registry-pre-v1-*` sibling before its active v1 registry was reseeded from
flake identity truth.

Phase 4 has not yet been deployed to the live cluster.

## Leader Enrollment

For each leader:

1. Inspect the flake-derived requirement with
   `clusterctl identity matrix --service ipns-publisher`.
2. Run
   `clusterctl identity generate-missing --service ipns-publisher --no-publish`.
3. Review the generated public inventory record and encrypted SOPS ledger.
4. Rebuild the leader and inspect `cluster-identity-ipns-key.service` before
   starting `cluster-identity-publish.service`.

The requirement and generator are declared by the
`system/cluster-identity` dendrite. Never commit an unencrypted PEM or generate
a replacement during rebuild. A changed IPNS name is a bootstrap trust change
and must be deployed deliberately.

## Testing

Run the focused Python verifier and publisher tests:

```bash
PYTHONPATH=tools/clusterctl python -m unittest discover \
  -s tools/clusterctl/tests -v
```

Run the repository Nix check:

```bash
nix build .#checks.x86_64-linux.cluster-identity-registry-v1
```

Run the isolated MicroVM scenario:

```bash
nix run ./experiments/cluster-identity-microvm#test
```

The MicroVM test generates ephemeral signing and IPNS keys outside the Nix
store, verifies conflict freezing, boots a Kubo publisher, imports the IPNS
key, publishes the signed snapshot, and then boots a fresh follower. The
follower resolves the head, verifies and caches the snapshot, pins its CID,
records its checkpoint, and materializes accepted state.

The Python and Nix checks additionally verify signed PubSub announcement
construction, tamper and stale-replay rejection, accepted-head deduplication,
and triggering of the existing fetch unit.

### Known Issues

The last MicroVM boot (`ipfs-publisher`) sometimes does not power off promptly
after its scenario script finishes, even though the script already wrote its
success marker into the shared directory. This is qemu/host shutdown
flakiness in the sandbox, not a registry or `clusterctl` bug. If `nix run
./experiments/cluster-identity-microvm#test` appears to hang at the
`ipfs-publisher login:` console prompt, check
`/tmp/cluster-identity-microvm/ipfs-success` and `/tmp/cluster-identity-microvm/success`
before assuming a logic failure — if both exist, the scenario already passed
and only the VM teardown is stuck.

### Debugging Tips

- **Always confirm `pwd` before `nix run ./experiments/...`.** A stray `cd`
  earlier in a long session silently breaks the relative flake reference and
  produces a one-line `error: getting status of "..."` instead of running
  anything. Prefer an absolute path if the working directory is in doubt.
- **Check for leftover qemu processes before starting a new run:**
  `ps aux | grep -E "qemu|microvm-test"`. Two invocations sharing
  `/tmp/cluster-identity-microvm` at the same time look like a hang but are
  actually resource contention; kill stale processes and `rm -rf
  /tmp/cluster-identity-microvm` before retrying.
- **To find which command inside a scenario step is failing**, temporarily
  add `exec >/shared/${role}.log 2>&1` and `set -x` to the
  `systemd.services.registry-scenario.script` in `microvm-test.nix`, rebuild,
  rerun, then read `/tmp/cluster-identity-microvm/<role>.log`. The qemu
  serial console is `quiet`-booted and easy to misread; the log file in the
  shared directory is authoritative. Revert this instrumentation once the
  real fix lands — it should never be part of the committed diff.
- **Capture the exit code right after the command, not after a pipe.**
  `nix run ... | tail -5; echo $?` reports `tail`'s exit code, not the test's.
- **Trust the marker files over the console tail.** If
  `/tmp/cluster-identity-microvm/{success,ipfs-success}` already exist, the
  scenario logic has already passed even if the console still shows a login
  prompt or the wrapper process hasn't exited yet.
