# Identity Registry Transport

The registry transport is Git-first, with Radicle as secondary replication and
host-bootstrap SSH paths as repair fallback. The registry transports the live
projection of flake-declared identity state; it is not where identity truth is
invented.

## Primary

Git over SSH over the private Yggdrasil mesh is the preferred path once a node
has working live identity data.

## Secondary

Radicle is the decentralized replication path. It should carry the same signed
registry data, but Radicle availability is not required for trust. Declare a
Radicle remote in `inventory/identity-policy.nix` only after the real `rad://`
identity exists.

## Fallback

Fallback SSH uses `inventory/host-bootstrap.nix` fields:

- `targetHost`
- `identityFile`
- `sshUser`
- `deploymentTransport`
- `operatorCapable`

This keeps repair routes available when the live overlay identity is broken.

## Fetch And Notify

Followers fetch on `cluster-identity-fetch.timer`. Leaders push after
successful `clusterctl` operations, also push on `cluster-identity-push.timer`,
and can notify nodes to fetch immediately.

Notifications are acceleration only. Timers provide eventual convergence.

The normal leader operation is:

```bash
clusterctl identity publish
```

That command fetches configured registry remotes, publishes missing events from
`inventory/identities.nix`, reconciles materialized state, and pushes configured
registry remotes. It does not invent per-key state at the registry layer.

## Commands

```bash
clusterctl identity publish
clusterctl registry remotes sync
clusterctl registry sync
clusterctl registry push
clusterctl registry notify
systemctl start cluster-identity-fetch-now.service
systemctl status cluster-identity-fetch.timer
```

Followers use `git fetch --all --prune`, then compute trusted state from
signed events that mirror the flake identity inventory. They do not use
uncontrolled `git pull` and do not treat Git merge history as the trust model.

## Expected Remotes

```text
leader-r640-0-ygg
leader-desktoptoodle-ygg
leader-r640-0-fallback
leader-desktoptoodle-fallback
```

`clusterctl registry remotes sync` reconciles the Git remote set from
`inventory/identity-policy.nix`. `clusterctl registry sync` and
`clusterctl registry push` sync those remotes by default before fetching or
pushing.
