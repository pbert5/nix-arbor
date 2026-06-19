# Registry Architecture

## Problem

The flake is the durable source of cluster shape:

- hosts, users, roles, and networks
- hardware and storage facts
- dendrite and fruit selection
- service enablement
- leader and registry policy
- deploy-rs and Colmena outputs
- fallback bootstrap paths

The registry is not the source of information. It is a live projection that lets
nodes consume flake-declared identity facts without waiting for every machine to
rebuild.

This matters during repair. If a host changes Yggdrasil identity, SSH host key,
Radicle node ID, or git-annex endpoint, the new fact should be declared in the
flake, mirrored into the registry, and learned by other nodes at runtime.

## Layering

```text
flake inventory and modules
  stable cluster shape, identity ledgers, policy, fallback paths,
  service enablement

live identity registry
  signed event log mirroring flake identities, private-delivery metadata,
  receipts, generated state

runtime materialization
  /run/cluster-identity files consumed by SSH, Yggdrasil, Radicle,
  git-annex, deploy wrappers, and repair tooling
```

## Source-Of-Truth Boundary

The flake owns:

- public identity source records in `inventory/identities.nix`
- private identity ledger paths and encryption policy metadata
- SOPS-encrypted private service identity material
- SOPS-encrypted host age private key recovery material
- which hosts are leaders
- which services consume live identity data
- registry path and materialized path
- promotion and receipt policy
- fallback bootstrap paths
- deploy-rs and Colmena outputs

The registry mirrors:

- current Yggdrasil addresses
- SSH host public keys
- Radicle node IDs
- git-annex endpoint metadata
- deprecated fallback identities
- burned or compromised identities
- pending private identity delivery metadata
- receipts and acknowledgements from target nodes

The registry must be rebuildable from flake identity state plus any retained
event history that operators choose to preserve for audit.

## Roles

### Leaders

Leaders can:

- read leader-encrypted SOPS ledgers
- publish flake identity records into registry events
- commit and push registry updates
- notify followers to fetch now
- deliver private material in the MVP
- collect receipts from target nodes
- promote staged identities to active
- burn compromised identities

Initial leaders:

```text
r640-0
desktoptoodle
```

### Followers

Followers can:

- fetch registry remotes
- verify registry events
- reconcile materialized state
- apply local runtime files
- write local receipts for their own private material

Followers do not push registry events in the MVP.

## Transport

Transport only moves data. Trust comes from flake-declared identity records,
trusted leader policy, signed registry events, timestamps, receipts, and burn
records.

Primary transport:

```text
Git over SSH over Yggdrasil from leaders
```

Secondary transport:

```text
Radicle
```

Fallback transport:

```text
Git over SSH over host-bootstrap paths
```

Expected remotes:

```text
leader-r640-0-ygg
leader-desktoptoodle-ygg
radicle
leader-r640-0-fallback
leader-desktoptoodle-fallback
```

Followers should fetch and reconcile. They should not use uncontrolled
`git pull` as the trust operation.

## Registry Layout

The MVP registry lives at:

```text
/var/lib/cluster-identity/registry
```

Layout:

```text
/var/lib/cluster-identity/registry/
  events/
  receipts/
  bundles/
  state/
  policy/
  README.md
```

- `events/` contains leader-authored identity events.
- `receipts/` contains node acknowledgements.
- `bundles/` is reserved for encrypted private delivery bundles.
- `state/` is generated and can be rebuilt from events and receipts.
- `policy/` contains registry-local schema notes.

The trusted leader policy is generated from the flake into:

```text
/etc/cluster-identity/policy.json
```

## Materialized Layout

Trusted runtime state is materialized under:

```text
/run/cluster-identity/
  active.json
  staged.json
  deprecated.json
  burned.json
  ssh_known_hosts
  yggdrasil/
    peers.json
  radicle/
    nodes.json
  git-annex/
    remotes.json
```

Consumers should treat these files as runtime state. They can be regenerated
from the registry at any time.
