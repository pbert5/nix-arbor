# Storage Fabric Components

This page describes the moving parts that make up the storage fabric and the job
each part is expected to do.

## Component summary

| Component | Purpose | Key capability flags | Current hosts |
|---|---|---|---|
| `git-annex` | durable content identity and copy policy | `annex-storage`, `annex-client`, `annex-workstation`, `annex-compute-cache` | `r640-0`, `desktoptoodle` |
| SeaweedFS hot pool | fast active working set | `seaweed-master`, `seaweed-volume`, `seaweed-filer`, `seaweed-s3` | `r640-0`, `desktoptoodle` |
| archive backends | durable long-term copies | `archive-node` | `r640-0` (NAS) |
| Radicle seed | metadata replication over private Ygg | `radicle-seed` | `r640-0`, `desktoptoodle` |
| fabric observability | quick health and copy-safety checks | `storage-fabric-observer` | `r640-0`, `desktoptoodle` |

## `git-annex`

`git-annex` is the source of truth for content identity, copy counts, and copy
location tracking.

### Important paths and defaults

- repo root: `/srv/annex/cluster-data`
- service account defaults: user `annex`, group `annex`
- default `numcopies`: `2`
- metadata-only remotes default list: `radicle`, `github`

### Preferred-content groups

These defaults come from `inventory/storage-fabric.nix` and hosts opt into a
group through `org.storage.annex.group`.

| Group | Wanted | Required | Intended use |
|---|---|---|---|
| `archive` | `standard or (include=*.important)` | `standard` | durable storage nodes |
| `hot` | `present and (not unused)` | empty | active hot-pool helpers |
| `compute` | `inallgroups` | empty | short-lived compute caches |
| `workstation` | `present` | empty | user-facing working copies |
| `transient` | `nothing` | empty | manual or opt-in copies only |

### Helper CLI

The `storage/git-annex` dendrite ships the `cluster-annex` helper. Useful
commands include:

- `cluster-annex init`
- `cluster-annex set-group <group>`
- `cluster-annex add-remote <name> <host-alias>`
- `cluster-annex stage <project>`
- `cluster-annex job-stage <project> <job-id>`
- `cluster-annex job-publish <job-id>`
- `cluster-annex archive <path>`
- `cluster-annex drop-safe <path>`

See [`../operations/reference/command-reference.md`](../operations/reference/command-reference.md)
for the full command table.

### Transfer boundary

The private-transport policy expects annex content remotes to use private Ygg
host aliases such as `annex+ssh://r640-0-ygg/srv/annex/cluster-data`. Public Git
or Radicle URLs may exist for metadata, but they must not be used as content
remotes.

### P2P transports

The git-annex dendrite also provides optional P2P transport support:

- Tor is installed and enabled as a local client. A writable
  `/etc/tor/torrc` include exists for git-annex's built-in
  `git annex p2p --enable tor` setup path.
- Iroh support is available through the `git-annex-p2p-iroh` helper, backed by
  `dumbpipe` from the unstable package set because git-annex requires
  `dumbpipe` 0.33.0 or newer.
- `annex-remotedaemon` runs for initialized annex fabric hosts and serves any
  P2P networks enabled in the repo.

P2P pairing remains a repo-local git-annex action. See
[`../operations/reference/command-reference.md`](../operations/reference/command-reference.md)
for the exact commands.

## SeaweedFS hot pool

SeaweedFS is the active hot-pool layer. It is deliberately convenient rather
than authoritative.

### Roles and services

| Role | Main service | What it does |
|---|---|---|
| `seaweed-master` | `seaweedfs-master` | cluster coordinator and volume registry |
| `seaweed-volume` | `seaweedfs-volume` | stores Seaweed volume data |
| `seaweed-filer` | `seaweedfs-filer` and `seaweedfs-hot-mount` | filer namespace and `/hot` mount |
| `seaweed-s3` | Seaweed S3 gateway | optional S3-compatible access, currently disabled by default |

### Paths and ports

Default hot-pool settings come from `inventory/storage-fabric.nix`.

| Setting | Value |
|---|---|
| mount point | `/hot` |
| filer state path | `/srv/seaweedfs/filer` |
| volume state path | `/srv/seaweedfs/volumes` |
| master port | `9333` |
| filer port | `8888` |
| volume port | `8090` |
| S3 port | `8333` when enabled |
| gRPC companion ports | `port + 10000` |
| replication | `001` |

The firewall leaf opens these ports only on the Yggdrasil interface and asserts
that they are not exposed globally or on other interfaces.

### Hot-pool behavior

- `/hot` is a staging and working surface.
- project staging copies or links annex-managed content into the active working
  area.
- job helpers create per-job scratch areas under `/hot/scratch/<job-id>`.
- loss of `/hot` is an operational inconvenience, not a catalog disaster.

## Archive backends

Archive backends are enabled per host under `org.storage.annex.archive.*`.
Every `archive-node` must enable at least one backend.

### Supported backend shapes

| Backend | Per-host toggle | Required fact or field |
|---|---|---|
| NAS | `org.storage.annex.archive.nas.enable = true;` | `path` or `mountPoint` |
| tape | `org.storage.annex.archive.tape.enable = true;` | tape device facts under `facts.storage.tape.devices.*` |
| object | `org.storage.annex.archive.object.enable = true;` | private `endpoint` |
| removable disk | `org.storage.annex.archive.removableDisk.enable = true;` | `path` |

### Policy notes

The archive dendrite writes `/etc/cluster-annex/policy.conf` with:

- `numcopies`
- `minarchivecopies`

Those values document the intended safety rules, but the actual git-annex repo
policy still has to be initialized in the repo by `cluster-annex init` and the
usual annex commands.

### Current site usage

- `r640-0` enables the NAS archive path at `/mypool/annex-archive/nas`
- `desktoptoodle` does not currently enable an archive backend

Tape hardware notes live in
[`../../tape-library/hardware/README.md`](../../tape-library/hardware/README.md).

## Radicle seed

Radicle is used here as a metadata replication surface, not a payload carrier.

### Important settings

- role: `radicle-seed`
- service: `radicle-seed`
- private key path: `org.network.radicle.privateKeyFile`
- repo list: `org.network.radicle.repos` or `storageFabric.radicle.repos`
- default private port: `8776`

The service is enabled when the host has a seed role and a private key path is
configured. It binds to the host's private Yggdrasil address when one is known,
and the firewall opens the port only on the Ygg interface.

## Observability

The `storage-fabric-observer` role adds quick operator visibility.

### Current tools

- `fabric-status` for a fast summary of annex, SeaweedFS, and Radicle health
- daily annex health timer via the observability dendrite

`fabric-status` checks whether:

- the annex repo exists
- files are lacking copies
- remotes are configured
- the annex SSH key exists
- SeaweedFS services are active
- `/hot` is mounted
- `radicle-seed` is active

Use it as the first stop before deeper debugging.
