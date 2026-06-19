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

## Guide 1: Initialize Registry On First Leader

```bash
sudo mkdir -p /var/lib/cluster-identity/registry
sudo chown root:root /var/lib/cluster-identity/registry
sudo clusterctl registry init --registry /var/lib/cluster-identity/registry
sudo clusterctl registry validate --registry /var/lib/cluster-identity/registry
sudo clusterctl registry reconcile --registry /var/lib/cluster-identity/registry --out /run/cluster-identity
```

## Guide 2: Add Or Fetch Remotes

```bash
cd /var/lib/cluster-identity/registry
clusterctl registry remotes sync
git remote -v
git fetch --all --prune
clusterctl registry reconcile
```

## Guide 3: Publish The Flake Identity Ledger

```bash
clusterctl identity publish
clusterctl registry validate
clusterctl registry notify
```

`clusterctl identity publish` reads `inventory/identities.nix`, writes any
missing registry events, reconciles `/run/cluster-identity`, and pushes
configured registry remotes. Use `--node HOST` or `--service SERVICE` only when
you intentionally want to narrow the publish.

Leaders also run a best-effort publish during NixOS activation through the
`system/cluster-identity` dendrite. Keep using the explicit command for repair,
debugging, and immediate convergence after editing the identity ledger.

## Guide 4: Publish A Narrow Subset For Debugging

```bash
clusterctl identity publish --node r640-0
clusterctl identity publish --service yggdrasil

clusterctl registry notify --target r640-0
```

Low-level per-event commands such as `clusterctl identity publish-public` are
kept as escape hatches while the ledger publisher matures, but they are not the
normal operator path.

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
clusterctl bundle publish r640-0 yggdrasil \
  --generation 1 \
  --source ./private/r640-0-yggdrasil.key \
  --target-path /var/lib/yggdrasil/private.key

clusterctl receipt collect r640-0 yggdrasil --generation 1
clusterctl identity promote r640-0 yggdrasil --generation 1
clusterctl registry push
clusterctl registry notify
```

USB and PXE private-key delivery are intentionally out of scope for this MVP.

## Guide 8: Burn Compromised Identity

```bash
clusterctl identity burn r640-0 yggdrasil \
  --generation 1 \
  --fingerprint sha256:... \
  --reason "suspected compromise"

clusterctl registry push
clusterctl registry notify
```

## Guide 9: Follower Repair Sync

```bash
systemctl start cluster-identity-fetch-now.service
journalctl -u cluster-identity-fetch.service -n 100 --no-pager
clusterctl registry status
ls -R /run/cluster-identity
```

## Guide 10: Smoke-Test The Live Identity Rollout Path

Use the smoke test when you want a real end-to-end validation of:

- one-at-a-time staged and active rollout
- bulk rollout across a host set
- repeated stress rounds
- follower fetch/materialization on the easy-access verification hosts

The default target set is the operator-capable hosts from
`inventory/host-bootstrap.nix`, which currently means the Tailscale-reachable
leaders.

```bash
clusterctl identity smoke-test
clusterctl identity smoke-test --node r640-0 --node desktoptoodle
clusterctl identity smoke-test --node all --verify-node r640-0 --verify-node desktoptoodle
```

The command publishes synthetic smoke identities into the live registry,
verifies them on the selected verification hosts under `/run/cluster-identity`,
then burns the smoke identities so they do not remain active.

## Guide 11: Registry-Driven Deploy Dry Run

```bash
clusterctl deploy r640-0 --dry-run
clusterctl deploy desktoptoodle --dry-run
clusterctl deploy t320-0 --dry-run
```

The dry run should show active live registry targets, staged targets, deprecated
fallback targets, host-bootstrap fallback targets, and the selected target.
