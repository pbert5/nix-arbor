# Storage Fabric Architecture Overview

The storage fabric is the repo's large-data architecture for moving, caching,
replicating, and recovering content without treating every service as equally
trusted or equally durable.

## Design goals

- keep large content identity in `git-annex`
- keep active working data in a disposable hot pool
- keep long-term survival in explicit archive backends
- keep storage control and content transfer on the private Yggdrasil overlay
- keep Git and Radicle limited to metadata replication rather than payload
  transport

## Mental model

```text
Git / Radicle metadata
  -> tells the cluster what content exists and where it may live

git-annex
  -> names content, tracks copies, enforces drop safety

SeaweedFS hot pool
  -> stages active data for fast current work

Archive backends
  -> hold durable copies for long-term recovery
```

If one sentence has to win the cage match, it is this: **annex knows what the
content is, the hot pool makes current work convenient, and archives keep it
alive when convenience fails.**

## Responsibility by layer

| Layer | Purpose | Durability | Typical examples |
|---|---|---|---|
| Git metadata | repo history and config | permanent | flake repo, annex tracking branch |
| `git-annex` | file identity, location graph, copy policy | permanent | `whereis`, `numcopies`, preferred content |
| SeaweedFS `/hot` | active working set | disposable | staged projects, active datasets, job scratch |
| archive backends | long-term survival | durable | NAS, tape, future private object/removable media |
| local scratch | temporary compute workspace | disposable | per-job intermediate files |

## Control plane and data plane

### Metadata and control plane

These surfaces describe content or cluster state, but are not the primary
payload path:

- Git remotes such as GitHub
- Radicle seeds
- inventory and flake configuration
- validation and helper scripts
- archive manifests and restore evidence

### Content data plane

These surfaces carry or store actual content bytes:

- annex SSH remotes over `*-ygg` aliases
- SeaweedFS master, volume, filer, and optional S3 endpoints on the Yggdrasil
  interface only
- private archive endpoints such as the NAS path or tape backend

The private-transfer rule matters because a public Git remote is acceptable for
metadata, but not for annex content.

## Current deployment shape

| Host | What it currently owns |
|---|---|
| `r640-0` | SeaweedFS master, volume, filer, annex storage, NAS archive staging, Radicle seed, observer |
| `desktoptoodle` | SeaweedFS volume, filer, annex storage, Radicle seed, observer |

Operational implications:

- `r640-0` is the only host with `org.storage.seaweedfs.master = true` today.
- both service nodes enable `org.storage.seaweedfs.volume` capacity for the hot
  pool.
- the hot pool currently uses replication `001`, so the declared topology and
  inventory promises match.
- `desktoptoodle` does not currently expose a tape archive backend.

## Repository implementation map

| Area | File or path | What it owns |
|---|---|---|
| site defaults | `inventory/storage-fabric.nix` | transport policy, annex defaults, hot-pool defaults, archive defaults |
| host selection | `inventory/hosts.nix` | explicit dendrites plus storage-fabric `org.*` capability flags and overrides |
| helper library | `lib/storage-fabric.nix` | inventory helpers such as Ygg address lookup and capability discovery |
| validation | `lib/validation/storage-fabric.nix` | flake-check assertions for transport, topology, and backend facts |
| git-annex module | `dendrites/storage/dendrites/git-annex/` | repo root, helper CLI, SSH, users, private-transport policy |
| SeaweedFS module | `dendrites/storage/dendrites/seaweedfs-hot/` | master, volume, filer, mount, firewall, optional S3 |
| archive module | `dendrites/storage/dendrites/archive/` | archive-node assertions and archive policy notes |
| Radicle module | `dendrites/network/dendrites/radicle/` | seed config, service wiring, Ygg-bound firewall |
| observability | `dendrites/storage/dendrites/storage-observability/` | `fabric-status` and annex health checks |

## Normal content lifecycle

```text
1. Add or publish content into git-annex.
2. Sync metadata to peers or metadata remotes.
3. Stage active project or job inputs into /hot when needed.
4. Run compute or operator workflows against staged data.
5. Publish outputs back into annex.
6. Copy important outputs to archive remotes.
7. Drop or evict hot copies only when annex policy says it is safe.
```

The hot pool is intentionally rebuildable. If `/hot` disappears, the recovery
path is annex metadata plus surviving content copies, not wishful thinking and a
powerpoint.

## Read next

- For component-level behavior, see [`components.md`](./components.md).
- For inventory fields and host examples, see
  [`inventory-and-roles.md`](./inventory-and-roles.md).
- For operator procedures, see [`../operations/runbook.md`](../operations/runbook.md).
- For validation and security boundaries, see
  [`../policy/validation.md`](../policy/validation.md) and
  [`../policy/security.md`](../policy/security.md).
