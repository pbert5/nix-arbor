# Identity Registry Troubleshooting

## Not Sure Which Identities Should Exist

```bash
clusterctl identity matrix
clusterctl identity matrix --only-missing
clusterctl identity matrix --node HOST --service SERVICE
clusterctl identity generate-missing --dry-run
```

Use this first when the problem is not transport or signatures, but uncertainty
about whether a host should have a given identity at all. The matrix compares
the desired surface implied by inventory metadata to the current flake identity
source ledgers and prints the next operator commands for missing entries.

If a rebuild warning names missing identity source records for the current
host, run:

```bash
clusterctl identity generate-missing --node HOST
clusterctl identity matrix --node HOST
```

## Node Did Not Fetch

```bash
systemctl status cluster-identity-fetch.timer
systemctl start cluster-identity-fetch-now.service
journalctl -u cluster-identity-fetch.service -n 100 --no-pager
cat /var/lib/cluster-identity/local-state/fetch-status.json
cat /var/lib/cluster-identity/local-state/checkpoint.json
ipfs --api=/unix/run/ipfs.sock id
```

Inspect each leader result in `fetch-status.json`. `root-sequence-rollback`,
`same-sequence-equivocation`, and
`root-history-does-not-descend-from-last-good`,
`leader-event-chain-rollback`, and
`leader-event-chain-does-not-descend-from-last-good` are deliberate
rejections. The follower keeps its prior head and materialized state.

## Rebuild Prints HOME Or Host-Key Errors

```bash
cat /etc/cluster-identity/registry-known-hosts
cat /etc/cluster-identity/policy.json
sudo systemctl start cluster-identity-fetch.service
```

Receiving-host activation never publishes the flake identity ledger.
`clusterctl deploy` publishes from the deploying leader after a successful
deployment. Registry fetch and explicit publication run after networking is
available. Those paths export `HOME=/root` when required because the Kubo CLI
needs it even when using the configured Unix API socket.

Legacy registry SSH uses `/etc/cluster-identity/registry-known-hosts`, generated
from `inventory/identity-services/ssh-host.nix`,
`inventory/identity-services/yggdrasil.nix`, and
`inventory/host-bootstrap.nix`. If SSH reports an unknown host key for a leader
fallback IP or Yggdrasil address, confirm that file contains the target host,
fallback address, private Yggdrasil address, and SSH host key.

Git registry transport is disabled in default inventory. If explicitly enabled
for migration, its keys are host-local activation inputs. Prefer
`org.clusterIdentity.registryTransport.identityFile` when a leader should use a
machine-local key for live registry fetch or push; keep
`inventory/host-bootstrap.nix` focused on the operator-side deploy key.

## Registry Has Invalid Event

```bash
clusterctl registry validate --registry /var/lib/cluster-identity/accepted-registry
jq . /var/lib/cluster-identity/local-state/fetch-status.json
```

Check for missing `schema`, `eventId`, `subject.node`, `subject.service`,
integer `generation`, valid `state`, and a non-empty `signature`.

If every old event is missing v1 fields such as `clusterId`, `leaderSeq`,
`eventHash`, and `payloadHash`, preserve and reseed the legacy registry:

```bash
clusterctl registry ensure-v1
clusterctl identity publish --no-fetch --no-push
clusterctl registry validate
```

The old Git repository remains under a timestamped
`/var/lib/cluster-identity/registry-pre-v1-*` path.

## Registry Commit Reports Unknown Author

```bash
sudo git -C /var/lib/cluster-identity/registry config --local user.name "Cluster Identity Registry"
sudo git -C /var/lib/cluster-identity/registry config --local user.email "cluster-identity@localhost"
sudo git -C /var/lib/cluster-identity/registry add .
sudo git -C /var/lib/cluster-identity/registry commit -m "identity registry init"
```

Current `clusterctl` sets this repo-local identity automatically. Use the
commands above only for an already-initialized registry that was created before
that behavior was present.

## Signature Invalid

```bash
cat /etc/cluster-identity/policy.json
clusterctl registry validate
ssh-keygen -y -f "$(jq -r '.signingKeyPath' /etc/cluster-identity/policy.json)"
```

Registry validation verifies OpenSSH signatures in the `cluster-identity`
namespace. Confirm the event `leader`, event `leaderKey`, policy
`trustedLeaders`, and local `policy.signingKeyPath` agree. Placeholder
signatures are rejected unless policy explicitly enables
`allowPlaceholderSignatures`.

Trusted leader public keys come from `inventory/keys/leaders/`. The policy
normalizer trims those files to a single public-key line before comparing them
with event `leaderKey` values, so trailing newlines in the key files should not
cause false validation failures.

## Active Identity Not Materialized

```bash
clusterctl registry fetch-ipfs
jq . /var/lib/cluster-identity/accepted-registry/events/*/*.json
jq . /run/cluster-identity/active.json
ls -R /run/cluster-identity
```

If the event used private delivery, confirm the receipt exists.

## SSH Still Uses A Bootstrap Address Or Key

```bash
cat /run/cluster-identity/ssh_config
ssh -G HOST | grep -E '^(hostname|hostkeyalias|identityfile|identitiesonly) '
```

The live include must appear before the declarative fallback host blocks in
`~/.ssh/config`. Normal `HOST` and `HOST-ygg` aliases use the active registry
Yggdrasil endpoint. Home Manager conditionally offers keys declared in
`users.<name>.org.ssh.identityFiles` when they exist locally; this avoids
forcing a desktop-only key path on another leader. Use `HOST-bootstrap`
explicitly when the registry route is unavailable; it uses the inventory
bootstrap address and any explicitly declared bootstrap identity.

## Staged Identity Visible But Not Active

```bash
jq . /var/lib/cluster-identity/registry/state/staged.json
ls /var/lib/cluster-identity/registry/receipts
clusterctl receipt collect r640-0 yggdrasil --generation 1
clusterctl identity promote r640-0 yggdrasil --generation 1
```

## Burned Key Keeps Overriding Event

```bash
jq . /var/lib/cluster-identity/registry/state/burned.json
grep -R "sha256:" /var/lib/cluster-identity/registry/events
```

Publish a higher-generation replacement with a different fingerprint. Do not
reuse burned material.

## IPNS Head Unavailable

```bash
jq '.trustedLeaders | map_values(.ipnsName)' /etc/cluster-identity/policy.json
ipfs --api=/unix/run/ipfs.sock name resolve /ipns/LEADER_IPNS_NAME
cat /var/lib/cluster-identity/local-state/fetch-status.json
```

An unavailable head does not clear last-good state. Check Kubo connectivity and
the leader publisher timer; do not delete the local checkpoint to force an old
root through.

## PubSub Hint Did Not Trigger A Fetch

```bash
systemctl status cluster-identity-pubsub-listener.service
journalctl -u cluster-identity-pubsub-listener.service -n 100 --no-pager
jq . /var/lib/cluster-identity/local-state/pubsub-status.json
ipfs --api=/unix/run/ipfs.sock pubsub ls
ipfs --api=/unix/run/ipfs.sock pubsub peers \
  cluster-identity/user1-homelab/roots/v1
```

Check that Kubo has `Pubsub.Enabled = true`, the listener is subscribed to the
inventory topic, and at least one PubSub peer is visible. Rejected hints record
their last error in `pubsub-status.json`. A missed hint is not a convergence
failure: `cluster-identity-fetch.timer` continues polling trusted IPNS heads.
The listener reports `connectionState = "retrying"` while Kubo is restarting
and returns to `subscribed` without failing the system activation.

## Yggdrasil Path Broken

```bash
ip addr show ygg0
systemctl status yggdrasil
clusterctl deploy r640-0 --dry-run
```

Use the host-bootstrap fallback candidate for repair.

## Fallback SSH Path Used

```bash
nix eval --json .#inventory.hostBootstrap
clusterctl deploy desktoptoodle --dry-run
ssh root@100.64.0.10 true
```

Fallback paths come from `inventory/host-bootstrap.nix`.

## Deploy Target Cannot Be Resolved

```bash
clusterctl registry status
clusterctl deploy HOST --dry-run
jq . /run/cluster-identity/active.json
nix eval --json .#inventory.hostBootstrap.HOST
```

If no live target exists, fix `hostBootstrap.targetHost` first so repair access
does not depend on the broken live identity.
