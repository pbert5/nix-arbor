# Registry Phase 3 Test Handoff - 2026-06-23

This handoff covers the Phase 3 follower convergence implementation. It is
written for a separate agent or operator to run verification without needing
the implementation chat history.

## Scope Implemented

Phase 3 adds:

- trusted leader IPNS resolution through the configured Kubo API
- immutable snapshot fetch into a leader/CID cache
- full root, digest, policy, event-chain, manifest, and receipt validation
- explicit binding between the resolved leader name and `root.publisher`
- per-leader root sequence rollback and same-sequence equivocation rejection
- contiguous `previousRootCid` ancestry verification for newer observed roots
- leader-owned aggregation: a leader contributes its own signed event chain and
  bundle manifests, rather than selecting another leader's authored events
- reconciliation through the existing burn, generation, quorum, receipt,
  decryptability, conflict-freezing, and last-good logic
- persistent accepted head and CID checkpoints
- recursive Kubo pinning of accepted roots
- a fetch status record for operational diagnosis
- declarative Kubo and IPFS follower timers on NixOS leaders and followers
- an additional fresh follower role in the MicroVM scenario

Default Git/SSH and Radicle registry fetch flags are now false. The old command
paths remain available only for an explicit migration fallback.

## Important Paths

- Writable leader source registry:
  `/var/lib/cluster-identity/registry`
- Publisher snapshot workspace:
  `/var/lib/cluster-identity/publisher/snapshot`
- Follower immutable cache:
  `/var/lib/cluster-identity/follower-cache/<leader>/<cid>/`
- Follower accepted aggregate:
  `/var/lib/cluster-identity/accepted-registry/`
- Anti-rollback checkpoint:
  `/var/lib/cluster-identity/local-state/checkpoint.json`
- Last fetch evidence:
  `/var/lib/cluster-identity/local-state/fetch-status.json`
- Materialized runtime state:
  `/run/cluster-identity/`

The writable leader registry and accepted follower aggregate must remain
separate. A follower fetch must never rewrite a leader's unpublished source
events.

## Changed Code

- `tools/clusterctl/clusterctl/follower.py`
  owns head resolution, immutable caching, root ancestry, accepted aggregation,
  reconciliation, checkpoint updates, and fetch reporting.
- `tools/clusterctl/clusterctl/ipfs.py`
  adds strict IPNS result parsing and atomic `ipfs get` directory fetches.
- `tools/clusterctl/clusterctl/registry.py`
  exposes checkpoint helpers, preserves transport checkpoint fields during
  reconciliation, and rejects policy generation rollback.
- `tools/clusterctl/clusterctl/main.py`
  adds `clusterctl registry fetch-ipfs` and routes the default manual
  `clusterctl identity publish --push` path through IPFS/IPNS.
- `dendrites/system/dendrites/cluster-identity/cluster-identity.nix`
  enables Kubo for registry participants and makes the fetch timer IPFS-first.
- `inventory/identity-policy.nix`
  declares follower paths, resolve timeout, and IPFS-only default transport.
- `experiments/cluster-identity-microvm/`
  adds the fresh `ipfs-follower` role and shared test Kubo repository.

## Final Verification Status

Phase 3 passed every planned layer on 2026-06-23:

- Python suite: 13/13 pass
- Nix sandbox check: pass
- follower and leader module evaluation: pass
- `t320-0` full NixOS toplevel build: pass
- clean five-role MicroVM scenario: pass, exit 0

The MicroVM run produced all three success markers and messages. Its accepted
CID matched the publisher state, `leader-a` was checkpointed at root sequence
1, the accepted aggregate contained only `events/leader-a`, and the follower
materialized generation 2. No QEMU or test process remained afterward.

Two test defects were corrected during verification:

1. The two-head conflict unit test enrolled `leader-b` after building its
   snapshots, making their embedded policy projection stale. Enrollment now
   happens before snapshot construction; the intended generation conflict then
   reaches reconciliation and freezes at generation 1.
2. virtio-9p cannot honor Kubo's ownership and chmod operations for guest UID
   261 on a host-owned shared repository. The isolated Kubo test roles now run
   as root with XDG state redirected to `/shared/ipfs-xdg`. Production Kubo
   configuration is unchanged and continues to use its dedicated account.

The first `t320-0` build attempt was inherited from another agent and spent
over 30 minutes cycling remote builders because the desktop builder rejected
its SSH identity. That stale process was stopped. The same toplevel build then
completed locally with `--builders ''`; this was an infrastructure issue, not
a system configuration failure.

## Recommended Test Order

### 1. Static And Python Layer

```bash
git diff --check
PYTHONPATH=tools/clusterctl python -m unittest discover \
  -s tools/clusterctl/tests -v
```

Expected: 13 tests pass. Pay particular attention to:

- `test_follower_accepts_ipns_head_pins_and_materializes`
- `test_follower_rejects_same_sequence_equivocation_and_keeps_last_good`
- `test_follower_accepts_newer_root_descending_from_checkpoint`
- `test_follower_freezes_conflicting_generation_from_two_ipns_heads`

### 2. Nix Sandbox Check

```bash
nix build .#checks.x86_64-linux.cluster-identity-registry-v1
```

Expected: the same Python suite passes in the Nix sandbox.

### 3. NixOS Module Evaluation

Use one follower and one leader to catch option or systemd merge errors:

```bash
nix eval --json \
  .#nixosConfigurations.t320-0.config.services.kubo.enable
nix eval --json \
  .#nixosConfigurations.t320-0.config.systemd.timers.cluster-identity-fetch.timerConfig
nix eval --json \
  .#nixosConfigurations.r640-0.config.services.kubo.enable
```

Expected:

- Kubo is enabled on the follower and leader.
- the follower fetch timer exists
- generated policy contains `followerCachePath`, `acceptedRegistryPath`, and
  `registry.ipfs.api = "/unix/run/ipfs.sock"`
- default Git/SSH and Radicle transport flags are false

If evaluation is clean, build the narrower follower system before attempting a
fleet build:

```bash
nix build .#nixosConfigurations.t320-0.config.system.build.toplevel
```

### 4. MicroVM End-To-End Scenario

```bash
nix run ./experiments/cluster-identity-microvm#test
```

The scenario should now print all three success lines:

```text
MicroVM registry conflict test passed
MicroVM IPFS/IPNS publication test passed
MicroVM IPNS follower convergence test passed
```

Expected markers:

```bash
test -f /tmp/cluster-identity-microvm/success
test -f /tmp/cluster-identity-microvm/ipfs-success
test -f /tmp/cluster-identity-microvm/ipfs-follower-success
```

Expected Phase 3 assertions:

```bash
shared=/tmp/cluster-identity-microvm
cid=$(jq -r .rootCid "$shared/publisher-state/leader-a.json")
test "$(jq -r '.heads["leader-a"].cid' \
  "$shared/follower-state/checkpoint.json")" = "$cid"
test "$(jq -r '.nodes["node-a"].yggdrasil.generation' \
  "$shared/ipfs-follower-out/active.json")" = 2
jq -e --arg cid "$cid" '.acceptedCids | index($cid) != null' \
  "$shared/follower-state/checkpoint.json"
jq -e '.leaders["leader-a"].status == "accepted"' \
  "$shared/follower-state/fetch-status.json"
test -f "$shared/follower-cache/leader-a/$cid/root.json"
```

The accepted aggregate should contain leader A's authored chain and should not
import leader B's chain merely because leader A mirrored it:

```bash
test -d "$shared/accepted-registry/events/leader-a"
test ! -d "$shared/accepted-registry/events/leader-b"
```

## MicroVM Design Detail

The Phase 2 publisher and Phase 3 follower boot sequentially and share
`/tmp/cluster-identity-microvm/ipfs-repo` as Kubo's data directory. This keeps
the test deterministic and exercises real Kubo IPNS resolution, `ipfs get`, and
pinning without relying on the public DHT. It does not yet prove transfer
between two simultaneously networked independent Kubo peers.

Both Kubo roles require `shared.mount` before `ipfs.service`. If Kubo fails to
start, inspect that ordering and ownership of the shared repository first.
The isolated roles run Kubo as root with XDG state under `/shared/ipfs-xdg`
because virtio-9p cannot satisfy Kubo's ownership and chmod operations for the
normal service UID. This exception is test-only; production Kubo keeps its
dedicated account and managed state directory.

## Known Shutdown Caveat

The existing QEMU runner sometimes fails to exit promptly after the guest has
already written its success marker and powered down. Phase 3 adds one more
final VM, so check `ipfs-follower-success` before treating a console hang as a
registry failure. The Phase 2 notes are in
`plans/registry-microvm-test-2026-06-23.md`.

## Failure Triage

If IPNS resolution fails:

- confirm publisher and follower use `/shared/ipfs-repo`
- confirm both commands use `/unix/run/ipfs.sock`
- inspect the publisher state's CID and policy's leader IPNS name

If fetch succeeds but validation fails:

- inspect `<cache>/<leader>/<cid>/root.json`
- confirm `root.publisher` exactly matches the trusted leader attribute name
- run `clusterctl registry validate` directly against that cached directory

If the candidate is rejected after a previous acceptance:

- inspect `fetch-status.json`
- `root-sequence-rollback` means a lower sequence was served
- `same-sequence-equivocation` means the sequence was reused for another CID
- `root-history-does-not-descend-from-last-good` means the previous-CID chain
  could not reach the checkpointed head

If materialization is wrong:

- inspect `accepted-registry/events/`
- each publisher should contribute only its own event directory
- inspect subject generation and payload hashes in `conflicts.json`
- confirm `last-good/` still contains the prior accepted state

## Live Deployment Is Not Part Of This Test Pass

Do not deploy Phase 3 to the live cluster until the tests above pass and the
real leader IPNS names and SOPS-backed publishing keys are enrolled. A fresh
follower with no accepted head cannot converge when every leader lacks an
`ipnsName`; with Git transports disabled by default, its fetch service will
correctly fail and preserve any existing last-good state.
