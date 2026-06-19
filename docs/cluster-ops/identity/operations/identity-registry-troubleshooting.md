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
git -C /var/lib/cluster-identity/registry remote -v
```

## Rebuild Prints HOME Or Host-Key Errors

```bash
cat /etc/cluster-identity/registry-known-hosts
cat /etc/cluster-identity/policy.json
sudo systemctl start cluster-identity-fetch.service
```

Leader activation publishes the flake identity ledger and may fetch or push the
registry remotes. That activation path runs without relying on the caller's
shell home directory; it exports `HOME=/root` and writes Git global state to
`/var/lib/cluster-identity/gitconfig`.

Strict registry SSH uses `/etc/cluster-identity/registry-known-hosts`, generated
from `inventory/identity-services/ssh-host.nix`,
`inventory/identity-services/yggdrasil.nix`, and
`inventory/host-bootstrap.nix`. If SSH reports an unknown host key for a leader
fallback IP or Yggdrasil address, confirm that file contains the target host,
fallback address, private Yggdrasil address, and SSH host key.

Registry transport keys are host-local activation inputs. Prefer
`org.clusterIdentity.registryTransport.identityFile` when a leader should use a
machine-local key for live registry fetch or push; keep
`inventory/host-bootstrap.nix` focused on the operator-side deploy key.

## Registry Has Invalid Event

```bash
clusterctl registry validate --registry /var/lib/cluster-identity/registry
jq . /var/lib/cluster-identity/registry/events/*.json
```

Check for missing `schema`, `eventId`, `subject.node`, `subject.service`,
integer `generation`, valid `state`, and a non-empty `signature`.

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
ssh-keygen -y -f /home/example/.ssh/deploy_rsa
```

Registry validation verifies OpenSSH signatures in the `cluster-identity`
namespace. Confirm the event `leader`, event `leaderKey`, policy
`trustedLeaders`, and local `policy.signingKeyPath` agree. Placeholder
signatures are rejected unless policy explicitly enables
`allowPlaceholderSignatures`.

## Active Identity Not Materialized

```bash
clusterctl registry reconcile --registry /var/lib/cluster-identity/registry --out /run/cluster-identity
jq . /var/lib/cluster-identity/registry/state/active.json
ls -R /run/cluster-identity
```

If the event used private delivery, confirm the receipt exists.

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

## Radicle Remote Unavailable

```bash
git -C /var/lib/cluster-identity/registry remote -v
clusterctl registry remotes sync
clusterctl registry sync
```

Radicle is secondary and may not be configured until the real `rad://` identity
is known. If a Radicle remote is declared in `inventory/identity-policy.nix`,
verify that the generated Git remote URL matches that real identity. Use leader
Git over SSH or fallback SSH while Radicle is down.

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
