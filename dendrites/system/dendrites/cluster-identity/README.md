# `system/cluster-identity`

Live signed cluster identity registry agent.

Its `meta.nix` declares host-age, SSH-host, and `status-ipns` identities for
every selected host, plus `ipns-publisher` and `leader-user-ssh` identities for
leaders. The flake resolves these and other dendrite declarations under
`inventory.identityRequirements.byHost`; `clusterctl identity matrix` and
`clusterctl identity generate-missing` consume that surface.

## What It Does

This dendrite installs `clusterctl`, Kubo, Git, OpenSSH, SOPS, and `ssh-to-age`;
creates the local live registry directories; writes
`/etc/cluster-identity/policy.json` from `inventory/identity-policy.nix`;
configures `sops-nix` to use the host age key; runs a systemd timer that fetches
and materializes trusted registry state; and, on enrolled leaders, publishes
signed immutable snapshots through IPFS and IPNS after rebuilds and on a
persistent timer. Registry participants also subscribe to signed PubSub hints
that wake the same fetch service without changing its trust decisions.
When a host has an enrolled `status-ipns` identity, it also publishes a
node-signed status document through its own node-local IPNS key.

Leaders can also use `clusterctl identity matrix` to derive the desired
host/service identity surface from normalized inventory metadata and compare it
to the flake identity source ledgers before publishing, repairing, or rotating
identities.

When the missing identities are auto-discoverable, leaders can then run
`clusterctl identity generate-missing` to write the missing source records into
the declarative ledgers before publishing.

For `leader-user-ssh`, the generator derives the selected user marked with
`org.clusterIdentity.role = "leader"`, creates a host-specific Ed25519 key,
stores its public record in inventory, and encrypts its private half in the
shared SOPS identity ledger. Rebuilds install that key at
`~/.ssh/cluster-leader-ed25519` only on the matching leader host. The base SSH
leaf trusts all enrolled leader-user public keys for root SSH across the fleet.
On leaders, the declared user owns the working registry paths, joins the
`cluster-identity` and `ipfs` groups, and receives group-read access to the
root-owned host age key so normal `clusterctl` and Kubo API operations do not
require a blanket sudo re-exec.

The flake still owns service modules, hardware, leader policy,
registry paths, fallback bootstrap paths, and SOPS-encrypted private identity
ledgers. The live registry mirrors fast-changing public identity facts such as
Yggdrasil addresses, SSH host keys, Radicle IDs, git-annex endpoint metadata,
deprecated identities, burn records, pending private-delivery metadata, and
receipts.

## Module Options

- `my.clusterIdentity.enable`: enable the agent.
- `my.clusterIdentity.role`: `leader`, `follower`, or `bootstrap-only`.
- `my.clusterIdentity.registryPath`: default `/var/lib/cluster-identity/registry`.
- `my.clusterIdentity.materializedPath`: default `/run/cluster-identity`.
- `my.clusterIdentity.localStatePath`: persistent anti-rollback checkpoints,
  default `/var/lib/cluster-identity/local-state`.
- `my.clusterIdentity.snapshotPath`: canonical snapshot working directory.
- `my.clusterIdentity.publisherStatePath`: persistent root sequence and CID.
- `my.clusterIdentity.followerCachePath`: verified immutable snapshots keyed by
  leader and CID.
- `my.clusterIdentity.acceptedRegistryPath`: locally assembled accepted source
  content, separate from a leader's writable registry.
- `my.clusterIdentity.statusPublisherPath`: working directory for this node's
  signed IPNS status payload.
- `my.clusterIdentity.onionMirrorPath`: read-only signed heads and immutable
  snapshots served by an enrolled leader onion service.
- `my.clusterIdentity.trustedLeaders`: leader signing policy from inventory.
- `my.clusterIdentity.policy`: generation, receipt, and burn policy.
- `my.clusterIdentity.fetchInterval`: timer interval, default `2min`.
- `my.clusterIdentity.randomizedDelay`: timer jitter, default `30s`.
- `my.clusterIdentity.sopsDefaultFile`: leader-encrypted private identity ledger.
- `my.clusterIdentity.sopsAgeKeyFile`: host-local age identity for `sops-nix`.
- `my.clusterIdentity.signingKeyPath`: host-local OpenSSH private key used for
  registry event signatures.
- `my.clusterIdentity.ipnsKeyName`: local Kubo keystore name for the leader.
- `my.clusterIdentity.statusIpnsKeyName`: local Kubo keystore name for this
  node's status publisher, default `cluster-identity-status-HOST`.
- `my.clusterIdentity.ipnsKeySopsFile`: SOPS file containing the leader's PEM
  PKCS8 IPNS private key under its hostname. Publication stays disabled when
  this or the trusted inventory IPNS name is absent.
- `my.clusterIdentity.registryTransportIdentityFile`: host-local OpenSSH
  private key used for registry Git fetch and push transport. Defaults to
  `org.clusterIdentity.registryTransport.identityFile` when set, then the
  bootstrap deploy identity from `inventory/host-bootstrap.nix`.

## Files Created

- `/var/lib/cluster-identity`
- `/var/lib/cluster-identity/age`
- `/var/lib/cluster-identity/registry`
- `/var/lib/cluster-identity/local-state`
- `/var/lib/cluster-identity/publisher-state`
- `/var/lib/cluster-identity/publisher/snapshot`
- `/var/lib/cluster-identity/status-publisher/status`
- `/var/lib/cluster-identity/follower-cache`
- `/var/lib/cluster-identity/accepted-registry`
- `/var/lib/cluster-identity/onion-mirror`
- `/run/cluster-identity`
- `/etc/cluster-identity/policy.json`

Materialized outputs are expected under:

- `/run/cluster-identity/active.json`
- `/run/cluster-identity/staged.json`
- `/run/cluster-identity/deprecated.json`
- `/run/cluster-identity/burned.json`
- `/run/cluster-identity/conflicts.json`
- `/run/cluster-identity/ssh_config`
- `/run/cluster-identity/ssh_known_hosts`
- `/run/cluster-identity/yggdrasil/peers.json`
- `/run/cluster-identity/radicle/nodes.json`
- `/run/cluster-identity/git-annex/remotes.json`

## Systemd Units

- `cluster-identity-fetch.service`
- `cluster-identity-fetch.timer`
- `cluster-identity-fetch-now.service`
- `cluster-identity-pubsub-listener.service`
- `ipfs.service` on leaders and followers.
- `cluster-identity-ipns-key.service` on enrolled leaders.
- `cluster-identity-prepare-leader-state.service` before each leader publish.
- `cluster-identity-publish.service` on enrolled leaders.
- `cluster-identity-publish.timer` on enrolled leaders.
- `cluster-identity-status-publish.service` on enrolled status publishers.
- `cluster-identity-status-publish.timer` on enrolled status publishers.

The fetch timer resolves every enrolled trusted leader IPNS name, validates and
caches immutable roots, retains last-good state across unavailable or rejected
heads, pins accepted CIDs, and materializes the accepted aggregate. The
publication timer retries IPFS/IPNS publication even when no operator command
has just run. A successful publication emits a best-effort signed PubSub hint.
On a leader with an enrolled `onionMirror`, it also updates the local immutable
mirror and signed head. Tor maps onion port 80 to an Nginx listener bound only
to the inventory-declared loopback port. Followers use Tor SOCKS fallback only
after IPNS or IPFS fails, then run the unchanged verifier and anti-rollback
workflow.
The status timer publishes the node's materialized active, staged, deprecated,
burned, conflict, and accepted-head view as signed `status.json` content under
the enrolled `status-ipns` name. It does not affect reconciliation or
acceptance.
The leader-state preparation unit repairs ownership immediately before each
publish, preventing the timer from racing activation while root-owned registry
files are being reconciled. Kubo starts with its PubSub experiment flag
whenever PubSub transport is enabled.
The listener verifies the cluster, topic, trusted leader and IPNS bindings,
timestamp window, message shape, and OpenSSH signature before starting
`cluster-identity-fetch.service`. Missed or rejected hints do not affect timed
IPNS convergence. The listener reconnects internally when Kubo restarts or its
subscription drops, so a transient daemon transition does not fail NixOS
activation.

Receiving-host activation initializes leader state but never appends identity
events. After a successful `clusterctl deploy`, the deploying leader publishes
and reconciles its own flake ledger, then publishes the IPFS/IPNS root. This
keeps received state and stale target-side checkouts from becoming fresh
registry history. Pass `--no-publish-identities` only for an explicit
operator-approved exception.

Git transport code remains available for an explicit migration fallback, but
all Git/SSH and Radicle registry transport flags are disabled in default
inventory. Leader working registries may still use local Git history; followers
do not depend on it.

## Trust Model

IPFS, IPNS, PubSub, onion mirrors, transitional Git, and fallback SSH only move or locate
data. They are not the trust layer. Registry events must be signed by trusted
leaders, linked into per-leader hash chains, ordered by subject/service
generation, checked against local anti-rollback and receipt policy, and
overridden by burn records when a fingerprint is compromised.

Registry events, receipts, and sealed bundle manifests use OpenSSH signatures
in the `cluster-identity` namespace. Placeholder signatures are rejected by
default policy.

## Leader And Follower Behavior

Leaders write registry events and publish immutable roots. Followers fetch by
trusted IPNS name, verify root and object signatures, enforce per-leader root
ancestry, merge leader-authored chains, reconcile conflicts and burns, pin
accepted CIDs, and apply materialized runtime state.

PubSub never supplies an accepted head directly. Its signed message only asks
the follower to run that existing workflow.

An onion head can locate a candidate CID during an IPNS outage, but cannot make
that candidate authoritative. Its signature and root binding are checked
before the existing snapshot and checkpoint rules run.

To enroll a leader, first set
`org.clusterIdentity.onionMirrorService = true` and rebuild so Tor creates the
hidden-service key. Then run
`clusterctl identity generate-missing --node HOST --service onion-mirror`.
The generator records Tor's public service key in
`inventory/identity-services/onion-mirror.nix`, derives the onion address from
that key, and verifies it against the runtime hostname. The publisher verifies
the runtime Tor hostname against inventory before advancing the mirror head.

Mirror ingress is rate-limited as one aggregate Tor-facing endpoint:
concurrent requests, request rate and burst, per-connection bandwidth, and Tor
streams per rendezvous circuit are bounded by `registry.onion` policy.

If a host's desired identity source records are missing from the flake, rebuild
evaluation emits a warning that names the missing services and points operators
at `clusterctl identity generate-missing --node HOST`.

For `status-ipns`, the default generator creates or reuses a node-local Kubo
IPNS key over the leader SSH path and stores only the public IPNS name in
`inventory/identity-services/status-ipns.nix`. The private status key remains
in that node's Kubo keystore. If remote enrollment fails for a leader host, the
generator can create a SOPS-backed status key in the existing private identity
ledger; the host imports it with `cluster-identity-status-ipns-key.service`
before publishing status. This fallback is leader-only because that ledger is
encrypted to leader recipients.

## Service Interaction

- Home Manager includes `/run/cluster-identity/ssh_config` before declarative
  fallback host blocks, so active Yggdrasil identities update normal host and
  `HOST-ygg` routing without a rebuild.
- SSH uses `/run/cluster-identity/ssh_known_hosts` as a live known-hosts file.
- Yggdrasil consumers read `/run/cluster-identity/yggdrasil/peers.json`.
- Radicle consumers read `/run/cluster-identity/radicle/nodes.json`.
- git-annex consumers read `/run/cluster-identity/git-annex/remotes.json`.

This dendrite does not yet rewrite Yggdrasil, Radicle, or git-annex service
configuration directly. It materializes trusted data for those consumers.

## Status Acknowledgement Recovery

Use this playbook when `clusterctl identity matrix` shows a desired identity
stuck in `au`, when signed node statuses are reachable but stale, or after an
operator burn of an extra newer generation should allow the still-desired
lower generation to become active again.

First run the recovery on the affected node. Use the repo version of
`clusterctl` that contains the recovery fix, and disable remote builders so a
broken builder host cannot block local repair:

```bash
rtk nix run --option builders '' .#clusterctl -- registry reconcile
rtk systemctl start cluster-identity-status-publish.service
rtk nix run --option builders '' .#clusterctl -- identity matrix --service yggdrasil
```

`registry reconcile` rereads `/var/lib/cluster-identity/registry`, verifies the
signed ledger, and rewrites the materialized local views under
`/run/cluster-identity` plus last-good/checkpoint state under
`/var/lib/cluster-identity/local-state`. It does not rotate keys, deploy NixOS,
or publish status by itself. Start `cluster-identity-status-publish.service`
after reconcile so peers can observe the refreshed local state through this
node's status IPNS record.

If other nodes are still running an older `clusterctl`, build the fixed
operator copy locally and copy that store path before running reconcile
remotely:

```bash
rtk nix build --option builders '' .#clusterctl
CLUSTERCTL_STORE="$(rtk readlink -f result)"

HOST=r640-0
HOST_ADDR='200:db8::10'
SSH_KEY=/run/secrets/cluster-identity-leader-user-ssh
SSH_OPTS="-F /dev/null -i ${SSH_KEY} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o HostKeyAlias=${HOST}"

rtk env NIX_SSHOPTS="${SSH_OPTS}" \
  nix copy --no-check-sigs --to "ssh-ng://root@[${HOST_ADDR}]" ./result

rtk proxy ssh ${SSH_OPTS} "root@${HOST_ADDR}" \
  "${CLUSTERCTL_STORE}/bin/clusterctl registry reconcile && systemctl start cluster-identity-status-publish.service"
```

Repeat the remote block for each reachable status publisher that needs repair,
changing `HOST` and `HOST_ADDR`. The `-F /dev/null` form bypasses a broken
generated SSH include such as `/run/cluster-identity/ssh_config`; the explicit
`HostKeyAlias` keeps host-key checking tied to the inventory host name.

## Manual Testing

```bash
clusterctl identity matrix
clusterctl identity matrix --only-missing
clusterctl identity matrix --node "$(hostname)"
clusterctl identity generate-missing --dry-run
systemctl status cluster-identity-fetch.timer
systemctl status ipfs cluster-identity-ipns-key cluster-identity-publish.timer \
  cluster-identity-pubsub-listener.service
systemctl start cluster-identity-publish.service
journalctl -u cluster-identity-publish.service -n 100 --no-pager
systemctl start cluster-identity-fetch-now.service
journalctl -u cluster-identity-fetch.service -n 100 --no-pager
ls -R /run/cluster-identity
cat /etc/cluster-identity/policy.json
clusterctl registry status
clusterctl registry snapshot --publisher "$(hostname)"
clusterctl registry fetch-ipfs
clusterctl registry status-ipns-key ensure
clusterctl registry publish-status
cat /var/lib/cluster-identity/local-state/fetch-status.json
cat /var/lib/cluster-identity/local-state/status-publish.json
cat /var/lib/cluster-identity/local-state/pubsub-status.json
cat /var/lib/cluster-identity/local-state/checkpoint.json
clusterctl host-age public "$(hostname)"
```
