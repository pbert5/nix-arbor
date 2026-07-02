# Identity Registry Rollout Playbook

## Guide 0: Inspect The Desired Identity Matrix Before You Touch Anything

Use the matrix view first. It derives the desired machine/service identity
surface from normalized inventory metadata, then compares that desired state to
the current flake identity source ledgers.

```bash
clusterctl identity matrix
clusterctl identity matrix --only-missing
clusterctl identity matrix --node r640-0
clusterctl identity matrix --node t320-0 --service yggdrasil
clusterctl identity generate-missing --dry-run
```

The matrix uses services as rows and hosts as columns.

Desired rows are not hard-coded in `clusterctl`. Selected dendrites declare
their identity requirements and generator names in `meta.nix`; the flake
resolves them per host under `inventory.identityRequirements.byHost`.
Selecting the dendrite, plus any service-specific predicate declared in its
metadata, is the opt-in. Hosts do not repeat identity enable flags under
`org.clusterIdentity`.

```bash
nix eval '.#inventory.identityRequirements.byHost' --json | jq
```

Legend:

- `-`: the service is not desired on that host
- `missing`: inventory metadata says the host should have that identity, but
  the flake source ledger does not currently have it
- `gN/x`: the source ledger already has a record at generation `N` in state
  `x`
- `extra gN/x`: the source ledger has a record that current inventory metadata
  no longer implies

The command also prints a focused command guide for missing entries, or for the
single host/service pair you filter to. Use that as the operator-facing
formatter before adding a missing identity or rotating an existing one.

Hosts that select `system/cluster-identity` now also emit a rebuild warning
when their desired identity source records are missing. The warning points back
to:

```bash
clusterctl identity generate-missing --node HOST
clusterctl identity matrix --node HOST
```

Generation keeps flake edits owned by the invoking user. Its default
auto-publish step detects a root-only registry, materialized output, or signing
key and re-invokes only `identity publish` through `sudo`. Use `--no-publish`
when preparing source-ledger changes that should not be published yet.

## Guide 1: Initialize Registry On First Leader

```bash
sudo mkdir -p /var/lib/cluster-identity/registry
sudo chown root:root /var/lib/cluster-identity/registry
sudo clusterctl registry ensure-v1 --registry /var/lib/cluster-identity/registry
sudo clusterctl registry validate --registry /var/lib/cluster-identity/registry
sudo clusterctl registry reconcile --registry /var/lib/cluster-identity/registry --out /run/cluster-identity
```

`ensure-v1` preserves an incompatible legacy registry by moving it to a
timestamped sibling such as
`/var/lib/cluster-identity/registry-pre-v1-20260623T...Z`, then initializes a
clean v1 registry. Leader activation runs this migration before republishing
the current flake identity ledger.

## Guide 2: Enroll And Inspect Leader IPNS Heads

```bash
clusterctl identity matrix --service ipns-publisher
clusterctl identity generate-missing --service ipns-publisher --dry-run
clusterctl identity generate-missing --service ipns-publisher --no-publish
jq '.trustedLeaders | map_values(.ipnsName)' /etc/cluster-identity/policy.json
systemctl status ipfs cluster-identity-ipns-key.service cluster-identity-publish.timer
clusterctl registry publish-ipfs --publisher "$(hostname)"
```

The generator creates one stable Ed25519 IPNS key per missing leader, stores
the public `k51...` name in
`inventory/identity-services/ipns-publisher.nix`, encrypts the private PEM into
`inventory/keys/leaders/leader-ipns-keys.sops.yaml`, and stages exactly those
two files so flake evaluation can see them. It may ask for sudo because the
leader host-age key is root-readable. A changed name is a bootstrap trust
change, not a routine rotation.

## Guide 3: Publish The Flake Identity Ledger

```bash
clusterctl identity publish
clusterctl registry validate
systemctl start cluster-identity-publish.service
```

`clusterctl identity publish` reads the normalized identity ledgers, writes any
missing registry events, burns stale same-leader live claims that are no longer
in inventory or have been replaced by a newer fingerprint, and reconciles local
state. Guarded services such as `host-age`, `ssh-host`, and IPNS identities are
skipped unless you pass `--burn-guarded-stale`. The leader publication service
builds the signed snapshot, advances IPNS, and emits a best-effort signed
PubSub hint. Use `--node HOST` or `--service SERVICE` only when you
intentionally want to narrow the publish. `clusterctl registry notify` remains
an SSH-triggered migration and repair fallback.

Leaders also run a best-effort publish during NixOS activation through the
`system/cluster-identity` dendrite. Keep using the explicit command for repair,
debugging, and immediate convergence after editing the identity ledger.

## Guide 3a: Enroll Leader Users

Users with `org.clusterIdentity.role = "leader"` receive one host-specific SSH
identity on every leader host that selects them:

```bash
clusterctl identity matrix --service leader-user-ssh
clusterctl identity generate-missing --service leader-user-ssh --dry-run
clusterctl identity generate-missing --service leader-user-ssh --no-publish
```

Generation writes public records to
`inventory/identity-services/leader-user-ssh.nix` and encrypts the private keys
into `inventory/keys/identities/cluster-private-identities.sops.yaml`. Deploy
the full fleet once so every host trusts the new public keys, then normal
`clusterctl deploy`, identity generation, publication, and registry inspection
run from the leader user. The old root deploy keys may stay trusted during
migration and recovery.

## Guide 4: Publish A Narrow Subset For Debugging

```bash
clusterctl identity publish --node r640-0
clusterctl identity publish --service yggdrasil

systemctl start cluster-identity-publish.service
```

Low-level per-event publication remains an internal test helper. It is not an
installed operator command.

## Guide 5: Edit Private Identity Ledgers

Private identity material lives in SOPS-encrypted files and is edited by
leaders:

```bash
nix run .#sops -- inventory/keys/identities/cluster-private-identities.sops.yaml
nix run .#sops -- inventory/keys/followers/host-age-private-keys.sops.yaml
```

The public ledger remains `inventory/identities.nix`. After changing public
facts or delivery metadata, publish the flake ledger:

```bash
clusterctl identity publish
```

Use the matrix again after the edit to confirm the desired host/service cell is
no longer `missing` before you publish:

```bash
clusterctl identity matrix --node HOST --service SERVICE
clusterctl identity generate-missing --node HOST --service SERVICE
clusterctl identity publish --node HOST --service SERVICE
```

To replace an existing identity with a new generation and swap the flake source
ledger in one step:

```bash
clusterctl identity rotate HOST SERVICE
clusterctl identity rotate HOST SERVICE --dry-run
```

For `host-age`, `rotate` updates `inventory/keys/host-age-recipients.nix`.
For other supported services, it updates the matching
`inventory/identity-services/<service>.nix` file.
The replacement generation is chosen above the highest generation known from
the flake ledger, materialized live state, and accepted registry events, so a
leader with stale desired inventory does not reuse a live generation. The
publish step burns older same-leader generations when the rotated fingerprint
changed.

## Guide 6: Enroll A Host Age Recipient

The host private age key stays on the host. The flake records only the public
recipient in `inventory/keys/host-age-recipients.nix`.

```bash
clusterctl host-age bootstrap HOST
clusterctl host-age public HOST
```

After recording the public recipient in the flake:

```bash
clusterctl identity matrix --node HOST --service host-age
clusterctl identity generate-missing --node HOST --service host-age
clusterctl identity publish
```

## Guide 7: SSH-Only Private Key Delivery

Prefer sealed registry bundles for private service material:

```bash
clusterctl bundle seal r640-0 yggdrasil \
  --generation 2 \
  --source ./private/r640-0-yggdrasil.key \
  --target-path /var/lib/yggdrasil/private.key \
  --from-inventory
```

Then add the generated `bundles/...manifest.json` path to the matching
`private.bundleManifest` field in `inventory/identities.nix`, publish the flake
ledger, and collect the receipt before promotion when policy requires it.

If you are narrowing work to one host/service pair, use the matrix as the
reference sheet before and after the change:

```bash
clusterctl identity matrix --node r640-0 --service yggdrasil
```

The direct SSH copy path remains available for repair:

```bash
clusterctl bundle emergency-publish r640-0 yggdrasil \
  --generation 1 \
  --source ./private/r640-0-yggdrasil.key \
  --target-path /var/lib/yggdrasil/private.key

clusterctl receipt collect r640-0 yggdrasil --generation 1
clusterctl identity promote r640-0 yggdrasil --generation 1
systemctl start cluster-identity-publish.service
```

USB and PXE private-key delivery are intentionally out of scope for this MVP.

## Guide 8: Burn Compromised Identity

```bash
clusterctl identity burn r640-0 yggdrasil \
  --generation 1 \
  --fingerprint sha256:... \
  --reason "suspected compromise"

systemctl start cluster-identity-publish.service
```

## Guide 9: Follower Repair Sync

```bash
systemctl start cluster-identity-fetch-now.service
journalctl -u cluster-identity-fetch.service -n 100 --no-pager
clusterctl registry status
cat /var/lib/cluster-identity/local-state/fetch-status.json
cat /var/lib/cluster-identity/local-state/checkpoint.json
ls -R /run/cluster-identity
```

## Guide 10: Smoke-Test The Live Identity Rollout Path

Use the smoke test when you want an end-to-end validation of signed snapshot
publication, IPNS resolution, follower verification, anti-rollback checkpoint
advancement, and materialization.

The default target set is the operator-capable hosts from
`inventory/host-bootstrap.nix`, which currently means the Tailscale-reachable
leaders.

```bash
clusterctl identity smoke-test
clusterctl identity smoke-test --verify-node r640-0 --verify-node desktoptoodle
```

The command republishes the current registry without creating synthetic
identities, then waits until every selected host accepts the exact CID and root
sequence.

## Guide 11: Registry-Driven Deploy Dry Run

```bash
clusterctl deploy r640-0 --dry-run
clusterctl deploy desktoptoodle --dry-run
clusterctl deploy t320-0 --dry-run
```

The dry run should show active live registry targets, staged targets, deprecated
fallback targets, host-bootstrap fallback targets, and the selected target.
