# `system/cluster-identity`

Live signed cluster identity registry agent.

## What It Does

This dendrite installs `clusterctl`, Git, OpenSSH, SOPS, and `ssh-to-age`;
creates the local live registry directories; writes
`/etc/cluster-identity/policy.json` from `inventory/identity-policy.nix`;
configures `sops-nix` to use the host age key; runs a systemd timer that fetches
and materializes trusted registry state; and, on leaders, publishes the flake
identity ledger during activation.

Leaders can also use `clusterctl identity matrix` to derive the desired
host/service identity surface from normalized inventory metadata and compare it
to the flake identity source ledgers before publishing, repairing, or rotating
identities.

When the missing identities are auto-discoverable, leaders can then run
`clusterctl identity generate-missing` to write the missing source records into
the declarative ledgers before publishing.

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
- `my.clusterIdentity.trustedLeaders`: leader signing policy from inventory.
- `my.clusterIdentity.policy`: generation, receipt, and burn policy.
- `my.clusterIdentity.fetchInterval`: timer interval, default `2min`.
- `my.clusterIdentity.randomizedDelay`: timer jitter, default `30s`.
- `my.clusterIdentity.sopsDefaultFile`: leader-encrypted private identity ledger.
- `my.clusterIdentity.sopsAgeKeyFile`: host-local age identity for `sops-nix`.
- `my.clusterIdentity.flakePath`: local checkout used by leader auto-publish.
- `my.clusterIdentity.signingKeyPath`: host-local OpenSSH private key used for
  registry event signatures.
- `my.clusterIdentity.registryTransportIdentityFile`: host-local OpenSSH
  private key used for registry Git fetch and push transport. Defaults to
  `org.clusterIdentity.registryTransport.identityFile` when set, then the
  bootstrap deploy identity from `inventory/host-bootstrap.nix`.
- `my.clusterIdentity.autoPublishOnActivation`: publish identities during
  leader activation, default true for leaders.

## Files Created

- `/var/lib/cluster-identity`
- `/var/lib/cluster-identity/age`
- `/var/lib/cluster-identity/registry`
- `/run/cluster-identity`
- `/etc/cluster-identity/policy.json`

Materialized outputs are expected under:

- `/run/cluster-identity/active.json`
- `/run/cluster-identity/staged.json`
- `/run/cluster-identity/deprecated.json`
- `/run/cluster-identity/burned.json`
- `/run/cluster-identity/ssh_known_hosts`
- `/run/cluster-identity/yggdrasil/peers.json`
- `/run/cluster-identity/radicle/nodes.json`
- `/run/cluster-identity/git-annex/remotes.json`

## Systemd Units

- `cluster-identity-fetch.service`
- `cluster-identity-fetch.timer`
- `cluster-identity-fetch-now.service`
- `cluster-identity-push.service` on leaders.
- `cluster-identity-push.timer` on leaders.

The fetch timer gives eventual convergence. The push timer keeps leader remotes
moving even when no operator command has just run. The `fetch-now` unit is used
by leaders as an acceleration path after they push registry updates.

Leaders also run `clusterctl identity publish` from activation when
`my.clusterIdentity.autoPublishOnActivation` is enabled. The activation hook is
best-effort so a missing checkout or transient registry transport issue does
not block system activation.

## Trust Model

Git, Radicle, SSH over Yggdrasil, and fallback SSH only move data. They are not
the trust layer. Registry events must be signed by trusted leaders, ordered by
subject/service generation, checked against receipt policy, and overridden by
burn records when a fingerprint is compromised.

Registry events, receipts, and sealed bundle manifests use OpenSSH signatures
in the `cluster-identity` namespace. Placeholder signatures are rejected by
default policy.

## Leader And Follower Behavior

Leaders can write registry events, push Git remotes, and notify nodes to fetch.
Followers fetch, validate, reconcile, materialize, and apply local runtime
state. Followers do not push to the registry in this MVP.

If a host's desired identity source records are missing from the flake, rebuild
evaluation emits a warning that names the missing services and points operators
at `clusterctl identity generate-missing --node HOST`.

## Service Interaction

- SSH can use `/run/cluster-identity/ssh_known_hosts` as a live known-hosts file.
- Yggdrasil consumers read `/run/cluster-identity/yggdrasil/peers.json`.
- Radicle consumers read `/run/cluster-identity/radicle/nodes.json`.
- git-annex consumers read `/run/cluster-identity/git-annex/remotes.json`.

This dendrite does not yet rewrite Yggdrasil, Radicle, or git-annex service
configuration directly. It materializes trusted data for those consumers.

## Manual Testing

```bash
clusterctl identity matrix
clusterctl identity matrix --only-missing
clusterctl identity matrix --node "$(hostname)"
clusterctl identity generate-missing --dry-run
systemctl status cluster-identity-fetch.timer
systemctl start cluster-identity-fetch-now.service
journalctl -u cluster-identity-fetch.service -n 100 --no-pager
ls -R /run/cluster-identity
cat /etc/cluster-identity/policy.json
clusterctl registry status
clusterctl registry remotes sync
clusterctl host-age public "$(hostname)"
```
