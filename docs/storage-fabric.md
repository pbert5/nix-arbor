# Storage Fabric

> **Design goal:** a private, Yggdrasil-bound storage fabric where git-annex
> tracks global data identity and copy policy, SeaweedFS provides the active
> hot pool, Radicle/GitHub sync metadata and config, and archive remotes
> provide durable long-term survival.

## Architecture overview

```text
Radicle / GitHub / Gitea
  = code + flake + git-annex metadata sync

git-annex
  = global file catalog, copy policy, location tracking

SeaweedFS hot pool
  = active distributed data pool for current datasets and outputs

Archive remotes
  = slow durable storage: tape, NAS, S3, external disks

Private Yggdrasil only
  = approved path for annex content transfers and storage control plane
```

## Data layer responsibilities

| Layer | Durability | What it holds | Can it forget? |
|-------|-----------|---------------|----------------|
| git-annex metadata | permanent | file identity, location graph, copy policy | no |
| Radicle / GitHub | permanent | Git commits, annex tracking branch | no |
| SeaweedFS hot pool | cache | active datasets, job staging, recent outputs | yes |
| Archive remotes | permanent | completed datasets, final outputs, manifests | only if another archive copy exists |
| Compute scratch | transient | intermediate job data | yes |

## Transfer policy

**No annex content transfer over public IPv4/IPv6.**

All content transfers must use private Yggdrasil:

- Annex SSH remotes use `*-ygg` host aliases only
- SeaweedFS API/S3/Filer ports and their gRPC companion ports are bound to
  the Yggdrasil interface
- Archive backends are not exposed publicly
- Radicle nodes bind to Yggdrasil addresses

This is enforced by:

- `lib/validation/storage-fabric.nix` at flake-check time
- `dendrites/storage/dendrites/git-annex/leaves/private-transport.nix` assertions
- `dendrites/storage/dendrites/seaweedfs-hot/leaves/firewall.nix` firewall rules
- `dendrites/network/dendrites/radicle/leaves/node.nix` bind address

## Inventory model

Site-wide defaults live in `inventory/storage-fabric.nix`.

Key fields:

```nix
storageFabric = {
  enable = true;
  transport.privateNetwork = "privateYggdrasil";
  transport.allowPublicContentTransfers = false;  # hard gate
  annex.repoRoot = "/srv/annex/cluster-data";
  annex.defaultNumCopies = 2;
  annex.metadataRemotes = [ "radicle" "github" ];
  seaweedfs.hotPool.enable = true;
  seaweedfs.hotPool.replication = "001"; # current two-volume hot pool
  archive.remotes.tape.enable = false;   # enable per host via org.*
  archive.remotes.nas.enable = false;
  archive.minArchiveCopies = 2;
};
```

Host-specific overrides live under `org.*` in `inventory/hosts.nix`:

```nix
org.storage.annex = {
  group = "archive";          # annex preferred-content group for this host
  sshKeys = [ "ssh-ed25519 AAAA..." ];
  archive.nas.enable = true;
  archive.nas.path = "/srv/annex/archive/nas";
};
org.network.radicle.repos = [ "flake-devbox" "cluster-data" ];
```

## Host roles

| Role | Dendrites activated | Purpose |
|------|-------------------|---------|
| `annex-client` | `storage/git-annex` | reads/writes annex content |
| `annex-storage` | `storage/git-annex` | stable content store, SSH transfer target |
| `seaweed-master` | `storage/seaweedfs-hot` | SeaweedFS cluster coordinator |
| `seaweed-volume` | `storage/seaweedfs-hot` | SeaweedFS storage contributor |
| `seaweed-filer` | `storage/seaweedfs-hot` | SeaweedFS filesystem namespace + S3 |
| `seaweed-s3` | `storage/seaweedfs-hot` | SeaweedFS S3 gateway when enabled |
| `archive-node` | `storage/archive` | durable long-term storage node |
| `radicle-seed` | `network/radicle` | mirrors flake and annex metadata repos |

## Annex preferred-content groups

| Group | Wanted policy | Notes |
|-------|-------------|-------|
| `archive` | final outputs, important datasets | must not drop below minArchiveCopies |
| `hot` | active projects, recent outputs | may evict old data |
| `compute` | current job inputs | narrow scope, cleaned after jobs |
| `workstation` | current project files, previews | user-managed |
| `transient` | nothing automatically | opt-in only |

## Annex repo layout

```text
/srv/annex/cluster-data/
  datasets/      — source data
  projects/      — active project files
  outputs/       — job outputs
  models/        — trained models, large artifacts
  manifests/     — copy manifests, checksums
  scratch/       — transient intermediate data
  archive/       — staging area for archive remotes
```

## SeaweedFS hot pool layout

```text
/hot/
  projects/      — active project files staged from annex
  datasets/      — active datasets
  outputs/       — job outputs before annex-add
```

Hot pool data is **not** the source of truth. git-annex tracks identity and
copy policy. The hot pool can be wiped and rebuilt from annex + archive.  The
`seaweedfs-hot` filer leaf mounts `/hot` with
`seaweedfs-hot-mount.service`.

## Workflow

```text
1. User adds data anywhere with: git annex add <path>
2. Annex metadata syncs through Radicle/GitHub (Git commits only).
3. Active data is pulled into SeaweedFS hot pool via cluster-annex get-active.
4. Compute job reads from hot pool or local NVMe.
5. Job writes outputs.
6. cluster-annex publish-output <job> adds outputs to annex.
7. cluster-annex archive <path> copies outputs to archive remotes.
8. Hot pool evicts stale data when policy allows.
9. cluster-annex drop-safe enforces numcopies before dropping.
```

## Dendrite structure

```text
dendrites/storage/dendrites/
  git-annex/          — annex installation, users, repo root, SSH, helpers
  seaweedfs-hot/      — SeaweedFS master, volume, filer, S3, firewall
  archive/            — durable remotes: NAS, tape, object, policies

dendrites/network/dendrites/
  radicle/            — Radicle node, seed config, private-overlay binding
```

## Lib and validation

```text
lib/storage-fabric.nix          — helper functions: yggAddressOf, hostsWithRole, ...
lib/validation/storage-fabric.nix  — flake-check assertions for fabric roles
```

Validation catches at `nix flake check` time:

- `annex-storage` host not on private Ygg
- SeaweedFS host not on private Ygg
- `archive-node` with no archive backend configured
- archive backends missing required path/device/endpoint facts
- `radicle-seed` not on private Ygg
- public-looking annex or object archive content remotes
- SeaweedFS replication settings that require more volume hosts than inventory declares
- SeaweedFS hot-pool paths that are not absolute
- enabled hot pools without master, volume, or filer roles
- multiple SeaweedFS masters in the current single-master design
- enabled SeaweedFS S3 gateways without a filer to serve

## Radicle split

| Via Radicle | Not via Radicle |
|-------------|----------------|
| Git commits | Annex content (files) |
| Annex tracking branch | Large dataset blobs |
| Inventory / policy / manifests | SeaweedFS data |
| Flake and bootstrap config | Archive content |

## Security posture

The current fabric is private-overlay first: annex content, SeaweedFS control
traffic, and Radicle seeding bind to private Yggdrasil addresses.  SeaweedFS
services run as `seaweedfs` with systemd sandboxing, annex SSH access is limited
with `git-annex-shell`, and public content remotes are rejected by validation.

See [storage-fabric-security.md](./storage-fabric-security.md) for the current
hardening profile and remaining M15 follow-up work.

## Annex cluster experiment

`experiments/git-annex-cluster/` tests git-annex's built-in cluster feature.
It is **not** wired into the main fabric. See that directory for the test plan
and promotion criteria.

## Status

See [storage-fabric-roadmap.md](./storage-fabric-roadmap.md) for milestones.
See [storage-fabric-runbook.md](./storage-fabric-runbook.md) for operator procedures.
See [storage-fabric-restore-drills.md](./storage-fabric-restore-drills.md) for M16 restore drills.
