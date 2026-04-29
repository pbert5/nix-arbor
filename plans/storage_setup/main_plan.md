I found `pbert5/flake-devbox`, and its current shape is already perfect for this: `inventory/` is the data model, `dendrites/` are reusable capabilities, `fruits/` are deployable long-running outcomes, and networking/deploy surfaces are generated from inventory. 

## Quick plan: add a “cluster data fabric” branch

### 0. Target architecture

```text
Radicle/GitHub/Gitea
  = code + flake + git-annex metadata sync

git-annex
  = global file catalog, copy policy, location tracking

SeaweedFS hot pool
  = active distributed data pool for current datasets and outputs

Archive remotes
  = slow durable storage, tape, NAS, S3, external disks

Private Yggdrasil only
  = allowed path for annex transfers and storage control plane
```

## 1. Add new inventory model

Add:

```text
inventory/storage-fabric.nix
```

Purpose:

```nix
{
  storageFabric = {
    enable = true;

    networks.privateTransport = "yggdrasil-private";

    annex = {
      repoRoot = "/srv/annex/cluster-data";
      defaultNumCopies = 2;
      metadataRemotes = [ "radicle" "github" ];
      allowPublicTransfers = false;
    };

    seaweedfs = {
      hotPool = {
        enable = true;
        replication = "001"; # or your chosen SeaweedFS replication strategy
        filerPath = "/srv/seaweedfs/filer";
        volumePath = "/srv/seaweedfs/volumes";
        s3.enable = true;
      };
    };

    archive = {
      remotes = {
        tape.enable = true;
        nas.enable = true;
        object.enable = false;
      };
    };
  };
}
```

Then have hosts opt into roles:

```nix
roles = [
  "annex-client"
  "annex-storage"
  "seaweed-master"
  "seaweed-volume"
  "seaweed-filer"
  "archive-node"
  "radicle-seed"
];
```

## 2. Add dendrites

Create these capability branches:

```text
dendrites/storage/dendrites/git-annex/git-annex.nix
dendrites/storage/dendrites/git-annex/meta.nix

dendrites/storage/dendrites/seaweedfs-hot/seaweedfs-hot.nix
dendrites/storage/dendrites/seaweedfs-hot/meta.nix

dendrites/storage/dendrites/archive/archive.nix
dendrites/storage/dendrites/archive/meta.nix

dendrites/network/dendrites/radicle/radicle.nix
dendrites/network/dendrites/radicle/meta.nix
```

The split should be:

```text
git-annex dendrite:
  installs git-annex
  creates annex repo path
  manages transfer restrictions
  provides helper scripts

seaweedfs-hot dendrite:
  runs master, volume, filer, and optional S3 services
  exposes only over private Yggdrasil/listen addresses
  creates hot pool mount/export points

archive dendrite:
  defines durable annex remotes
  tape/NAS/object storage hooks
  enforces copy-before-drop rules

radicle dendrite:
  installs radicle
  seeds flake repo
  optionally seeds annex metadata repo
  binds/advertises over private overlay only
```

## 3. Make git-annex the truth layer

Create one annex repo for cluster data metadata:

```text
/srv/annex/cluster-data
```

Recommended logical layout:

```text
cluster-data/
  datasets/
  projects/
  outputs/
  models/
  scratch-manifests/
  archive-manifests/
```

Use git-annex for actual file contents, not Git.

Basic policy:

```text
archive nodes:
  wanted = important data, final outputs, completed datasets

hot pool nodes:
  wanted = active datasets, recent outputs

compute nodes:
  wanted = current job inputs only

workstations:
  wanted = current projects, notebooks, previews, thumbnails

transient nodes:
  wanted = nothing automatically
```

Add a helper command:

```text
cluster-annex get-active <project>
cluster-annex stage-job <project> <job-id>
cluster-annex publish-output <job-id>
cluster-annex archive <path>
cluster-annex fsck-important
```

## 4. Use SeaweedFS as the hot pool, not the global brain

SeaweedFS should be the fast active layer:

```text
/hot
  current datasets
  current outputs
  job staging
  temporary shared project data
```

Do **not** treat it as the only durable source of truth.

Flow:

```text
1. User adds data anywhere with git-annex.
2. git-annex metadata syncs through Radicle/GitHub.
3. Active data gets pulled into SeaweedFS hot pool.
4. Compute jobs read/write from hot pool or local NVMe.
5. Outputs are annex-added.
6. Outputs are copied to archive remotes.
7. Hot pool can evict later.
```

## 5. Add archive remotes

Archive should be annex-managed.

Possible remotes:

```text
archive-tape
  backed by FossilSafe/LTFS/TL2000 later

archive-nas
  backed by TrueNAS/NFS/local disk

archive-object
  backed by SeaweedFS S3, Garage, MinIO, or external S3

archive-cold-disk
  removable disk annex remote
```

Important rule:

```text
Hot pool is allowed to forget.
Archive is not allowed to forget unless another archive copy exists.
```

Set default annex safety:

```text
numcopies = 2
important data = 2 or 3 copies
scratch data = 1 copy
reproducible intermediates = 1 copy or no archive
```

## 6. Radicle integration

Use Radicle for:

```text
flake repo mirror
annex metadata repo mirror
cluster bootstrap availability
local-first repo access over Yggdrasil
```

Do **not** push big annex content through Radicle unless there is a very specific reason.

Recommended split:

```text
Radicle:
  Git commits
  annex metadata branch
  inventory
  policies
  manifests

git-annex transfer remotes:
  SSH over Yggdrasil
  rsync over Yggdrasil
  SeaweedFS/S3 over Yggdrasil
  archive remotes
```

For the git-annex cluster feature:

```text
Phase 1:
  use normal git-annex remotes and preferred-content rules

Phase 2:
  test git-annex cluster behavior in experiments/

Phase 3:
  promote it only if it makes Radicle-backed metadata sync cleaner
```

I would not make the annex cluster feature foundational on day one. Make normal annex remotes work first, then add cluster abstraction after the transfer rules are stable.

## 7. Force annex transfers over private Yggdrasil

Add a hard policy:

```text
No annex content transfer over public IPv4/IPv6.
No annex SSH remote using non-Ygg hostnames.
No SeaweedFS API/S3/Filer listening on public interfaces.
No archive service exposed outside private overlay unless explicitly allowed.
```

Implementation pieces:

```text
Annex SSH remotes:
  use host-ygg names only

Nix firewall:
  allow SeaweedFS ports only on yggdrasil interface/address

SSH config:
  Match host *-ygg
    HostName <ygg-ip>
    User annex
    IdentitiesOnly yes

Annex validation:
  reject remotes whose URL does not match ssh://*-ygg/
```

Add a validation file:

```text
lib/validation/storage-fabric.nix
```

Checks:

```text
annex-storage hosts must be on private Yggdrasil
seaweedfs hosts must be on private Yggdrasil
archive-node hosts must have at least one archive backend
public transfer remotes are rejected unless explicitly allowed
hot pool replication requires at least N eligible hosts
radicle seed nodes must be on the private overlay
```

## 8. Suggested repo files to add

```text
docs/storage-fabric.md
docs/storage-fabric-runbook.md

inventory/storage-fabric.nix

dendrites/storage/dendrites/git-annex/
  git-annex.nix
  meta.nix
  scripts.nix
  systemd.nix
  validation.nix

dendrites/storage/dendrites/seaweedfs-hot/
  seaweedfs-hot.nix
  meta.nix
  master.nix
  volume.nix
  filer.nix
  s3.nix
  firewall.nix

dendrites/storage/dendrites/archive/
  archive.nix
  meta.nix
  annex-remotes.nix
  tape.nix
  nas.nix
  object.nix

dendrites/network/dendrites/radicle/
  radicle.nix
  meta.nix
  seed.nix
  service.nix

lib/storage-fabric.nix
lib/validation/storage-fabric.nix

experiments/git-annex-cluster/
  README.md
  test-plan.md
```

## 9. First milestone

Build the smallest useful version:

```text
One workstation:
  annex-client

One stable storage node:
  annex-storage
  seaweed-master
  seaweed-volume
  seaweed-filer
  archive-node
  radicle-seed

One compute node:
  annex-client
  seaweed-volume optional
```

Success test:

```text
1. Add a dataset from workstation.
2. Sync metadata through Radicle/GitHub.
3. Pull dataset onto storage node.
4. Stage it into SeaweedFS hot pool.
5. Compute node reads from hot pool.
6. Compute node writes output.
7. Output is annex-added.
8. Output is copied to archive.
9. Remove hot copy.
10. Restore from archive.
```

## 10. The clean one-line design goal for the repo

```text
flake-devbox should define a private, Yggdrasil-bound storage fabric where git-annex tracks global data identity and copy policy, SeaweedFS provides the active hot pool, Radicle/GitHub sync metadata and config, and archive remotes provide durable long-term survival.
```
