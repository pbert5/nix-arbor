Below is a complete milestone roadmap you can drop into something like:

```text
docs/storage-fabric-roadmap.md
```

It follows your repo’s existing style: add reusable capabilities as dendrites, put host/role data in `inventory/`, keep services as fruits only when they are named deployable outcomes, and add validation when requirements get strict. Your authoring guide already says new dendrites should live under `dendrites/<parent>/dendrites/<child>/` with a matching `.nix` and `meta.nix`, and that strict requirements should be added to validation. 

# Complete Storage Fabric Milestones

## M0: Write the design contract

**Goal:** define what the storage fabric is allowed to promise.

Add:

```text
docs/storage-fabric.md
docs/storage-fabric-roadmap.md
```

Define these guarantees:

```text
git-annex:
  global file identity
  copy policy
  location tracking
  metadata sync

SeaweedFS:
  active hot pool
  current datasets
  current outputs
  fast shared staging

Archive:
  durable long-term storage
  tape/NAS/object/disk remotes

Radicle:
  decentralized Git metadata mirror
  flake repo mirror
  optional annex metadata mirror

Yggdrasil:
  private transport only
  storage control plane
  annex content transfers
```

Done when:

```text
docs explain:
  what is durable
  what is cache
  what can be deleted
  what must never be deleted
  what happens when a node disappears
```

## M1: Add inventory schema for the storage fabric

**Goal:** make the whole fabric data-driven.

Add:

```text
inventory/storage-fabric.nix
```

Include:

```nix
{
  storageFabric = {
    enable = true;

    transport = {
      privateNetwork = "privateYggdrasil";
      allowPublicContentTransfers = false;
    };

    annex = {
      repoRoot = "/srv/annex/cluster-data";
      user = "annex";
      group = "annex";
      defaultNumCopies = 2;
      metadataRemotes = [ "radicle" "github" ];
    };

    seaweedfs = {
      hotPool = {
        enable = true;
        masterPort = 9333;
        filerPort = 8888;
        s3Port = 8333;
        volumePort = 8080;
        replication = "001";
      };
    };

    archive = {
      defaultRequiredCopies = 2;
      remotes = {
        nas.enable = false;
        tape.enable = false;
        object.enable = false;
        removableDisk.enable = false;
      };
    };
  };
}
```

Done when:

```text
inventory can describe:
  which hosts are annex clients
  which hosts hold durable annex content
  which hosts run SeaweedFS
  which hosts are archive nodes
  which hosts seed Radicle
  which network is trusted for transfers
```

## M2: Define host roles

**Goal:** avoid hardcoding services per host.

Add or extend:

```text
inventory/roles.nix
```

Roles:

```text
annex-client
annex-storage
annex-archive
annex-workstation
annex-compute-cache

seaweed-master
seaweed-volume
seaweed-filer
seaweed-s3

archive-node
archive-tape
archive-nas
archive-object

radicle-seed
radicle-client

storage-fabric-observer
```

Done when a host can opt in like:

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

## M3: Add git-annex dendrite

**Goal:** install and initialize the base annex environment.

Add:

```text
dendrites/storage/dendrites/git-annex/
  git-annex.nix
  meta.nix
  leaves/packages.nix
  leaves/users.nix
  leaves/repo-root.nix
  leaves/ssh.nix
  leaves/systemd.nix
  leaves/helpers.nix
```

This should:

```text
install git-annex
create annex user/group
create /srv/annex/cluster-data
configure SSH access for annex transfers
install helper scripts
optionally create systemd timers
```

Helper commands:

```text
cluster-annex-init
cluster-annex-sync
cluster-annex-get
cluster-annex-copy
cluster-annex-drop-safe
cluster-annex-fsck
cluster-annex-whereis
```

Done when:

```text
one machine can initialize the annex repo
another machine can clone/sync metadata
content can transfer over SSH
no public transfer path is configured
```

## M4: Private Yggdrasil transfer enforcement

**Goal:** make private Ygg the only approved content-transfer path.

Add:

```text
dendrites/storage/dendrites/git-annex/leaves/private-transport.nix
lib/validation/storage-fabric.nix
```

Rules:

```text
annex remotes must use:
  *-ygg host aliases
  yggdrasil IPv6 addresses
  explicitly approved private overlay names

annex remotes must not use:
  public IPv4
  public IPv6
  normal LAN hostnames unless explicitly allowed
  GitHub for annex content
  Radicle for annex content by default
```

SSH config shape:

```sshconfig
Host *-ygg
  User annex
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
```

Firewall behavior:

```text
SeaweedFS ports:
  allowed only on private Yggdrasil interface/address

SSH annex transfers:
  allowed only from private overlay peers

Archive APIs:
  not exposed publicly
```

Done when:

```text
bad annex remote URLs fail validation
SeaweedFS does not listen publicly
annex content transfer fails closed if private Ygg is unavailable
```

## M5: Create the cluster-data annex repo

**Goal:** establish the global file catalog.

Repo layout:

```text
/srv/annex/cluster-data/
  datasets/
  projects/
  outputs/
  models/
  manifests/
  scratch/
  archive/
```

Recommended annex groups:

```text
archive
hot
compute
workstation
transient
cloud
tape
nas
object
```

Recommended wanted rules:

```text
archive:
  final outputs, important datasets, manifests

hot:
  active projects, recent outputs

compute:
  current job inputs only

workstation:
  current project files, notebooks, previews

transient:
  nothing automatically

tape:
  completed datasets and frozen outputs
```

Done when:

```text
git annex whereis works from multiple machines
each machine has a group
each group has preferred content
numcopies is set
dropping unsafe content is blocked
```

## M6: Add archive dendrite

**Goal:** define durable storage remotes separate from the hot pool.

Add:

```text
dendrites/storage/dendrites/archive/
  archive.nix
  meta.nix
  leaves/base.nix
  leaves/nas.nix
  leaves/tape.nix
  leaves/object.nix
  leaves/removable-disk.nix
  leaves/policies.nix
```

Archive backend types:

```text
NAS archive:
  local mounted storage
  TrueNAS/NFS-backed path
  ZFS-backed path

Tape archive:
  FossilSafe/LTFS integration later
  manifest generation
  restore verification

Object archive:
  SeaweedFS S3
  Garage
  MinIO
  external S3 if allowed

Removable disk archive:
  offline git-annex special remote
```

Done when:

```text
annex can copy important data to archive
annex refuses to drop data below required copy count
archive remotes can be listed and health-checked
```

## M7: Add SeaweedFS hot-pool dendrite

**Goal:** create the active distributed data pool.

Add:

```text
dendrites/storage/dendrites/seaweedfs-hot/
  seaweedfs-hot.nix
  meta.nix
  leaves/packages.nix
  leaves/master.nix
  leaves/volume.nix
  leaves/filer.nix
  leaves/s3.nix
  leaves/firewall.nix
  leaves/systemd.nix
  leaves/health.nix
```

Roles map to services:

```text
seaweed-master:
  runs master

seaweed-volume:
  contributes storage

seaweed-filer:
  provides filesystem namespace

seaweed-s3:
  provides S3-compatible access
```

Mount/export goals:

```text
/hot
  SeaweedFS Filer mount or access point

/hot/projects
/hot/datasets
/hot/outputs
```

Done when:

```text
one master starts
one or more volume servers join
filer works
S3 endpoint works if enabled
all ports are private-overlay-only
```

## M8: Integrate git-annex with the hot pool

**Goal:** make SeaweedFS useful without making it the source of truth.

Two options:

```text
Option A:
  hot pool is a normal working tree/staging area

Option B:
  SeaweedFS S3 is a git-annex special remote
```

I would start with Option A.

Flow:

```text
annex repo:
  tracks identity and copy policy

/hot:
  active staging and outputs

job wrapper:
  pulls inputs from annex
  stages into /hot
  runs job
  annex-adds outputs
  copies outputs to archive
```

Done when:

```text
cluster-annex-stage <project> copies required files into /hot
cluster-annex-publish-output <job> annex-adds outputs
hot data can be deleted and restored from annex/archive
```

## M9: Add job staging workflow

**Goal:** make moving from local to cluster compute easy.

Add scripts:

```text
cluster-job-stage
cluster-job-run-local
cluster-job-run-remote
cluster-job-publish
cluster-job-clean
```

Workflow:

```text
1. select project
2. resolve required annex content
3. fetch from nearest available source
4. stage to /hot or local NVMe
5. run computation
6. write outputs
7. annex add outputs
8. sync metadata
9. copy durable outputs to archive
10. clean hot/scratch if policy allows
```

Done when:

```text
same project can run locally or on compute node
outputs land in a predictable annex path
interrupted jobs leave resumable manifests
```

## M10: Add Radicle dendrite

**Goal:** make metadata/config available without depending only on GitHub.

Add:

```text
dendrites/network/dendrites/radicle/
  radicle.nix
  meta.nix
  leaves/packages.nix
  leaves/node.nix
  leaves/seed.nix
  leaves/remotes.nix
  leaves/systemd.nix
```

Radicle should mirror:

```text
flake-devbox repo
cluster-data annex metadata repo
optional project repos
```

Do **not** use Radicle as the primary large-content transfer layer.

Done when:

```text
flake repo can be fetched through Radicle
annex metadata repo can be fetched through Radicle
Radicle service is reachable over private Ygg
GitHub can disappear and local metadata still syncs
```

## M11: Add annex metadata remote policy

**Goal:** keep Git/Radicle/GitHub and content remotes cleanly separated.

Metadata remotes:

```text
radicle
github
gitea optional
local peer Git remotes
```

Content remotes:

```text
annex SSH over Ygg
SeaweedFS/S3 over Ygg
NAS archive
tape archive
object archive
removable disks
```

Validation rules:

```text
GitHub:
  metadata allowed
  annex content forbidden unless explicitly allowed

Radicle:
  metadata allowed
  annex content experimental only

Ygg SSH:
  content allowed

SeaweedFS S3:
  content allowed only over private overlay
```

Done when:

```text
metadata sync and content sync are separate
public Git remotes cannot silently become content remotes
```

## M12: Add annex cluster experiment

**Goal:** test git-annex cluster features without making them core too early.

Add:

```text
experiments/git-annex-cluster/
  README.md
  test-plan.md
  cluster-layout.md
  commands.md
```

Test:

```text
clustered storage nodes
Radicle-backed metadata
preferred content behavior
drop safety
offline node behavior
restore behavior
```

Promotion criteria:

```text
works better than normal annex remotes
does not hide failure states
does not make Radicle content transfer messy
does not break private-Ygg-only policy
```

Done when:

```text
you know whether annex cluster belongs in mainline
mainline still works without it
```

## M13: Add observability

**Goal:** see where data is and whether the fabric is safe.

Add:

```text
dendrites/storage/dendrites/storage-observability/
  storage-observability.nix
  meta.nix
  leaves/annex-status.nix
  leaves/seaweedfs-status.nix
  leaves/archive-status.nix
  leaves/prometheus.nix
```

Expose:

```text
annex whereis summaries
missing copy count warnings
unsafe drop warnings
archive lag
hot pool capacity
SeaweedFS volume status
Ygg peer availability
Radicle seed status
```

Output targets:

```text
CLI summary
systemd health check
Prometheus textfile exporter
Grafana dashboard later
```

Done when:

```text
one command shows:
  what data is underprotected
  what archive is stale
  which nodes are missing
  whether hot pool is healthy
```

## M14: Add validation and fail-early checks

**Goal:** make misconfigured storage dangerousness obvious at flake-check time.

Extend:

```text
lib/validation.nix
lib/validation/storage-fabric.nix
```

Checks:

```text
annex-storage hosts must have private Ygg membership
seaweed hosts must have private Ygg membership
archive-node must define at least one backend
radicle-seed must be reachable on private overlay
public transfers are rejected by default
hot pool replication cannot promise survival without enough nodes
tape archive requires tape facts
NAS archive requires path facts
object archive requires endpoint facts
```

Done when:

```text
nix flake check catches:
  missing archive backend
  exposed SeaweedFS port
  invalid annex remote
  host claiming storage role without storage facts
```

## M15: Add security hardening

**Goal:** make the fabric safe enough to leave running.

Hardening:

```text
separate annex user
restricted SSH keys
no shell where possible
systemd sandboxing
private tmp
protect system
read/write paths only where needed
firewall deny by default
Ygg-only service binding
no secrets in metadata
SOPS/age for credentials
```

SeaweedFS hardening:

```text
bind to private addresses
do not expose admin APIs publicly
protect S3 credentials
separate service users
limit write paths
backup filer metadata if needed
```

Done when:

```text
compromising one service does not grant full host access
public network cannot hit storage APIs
credentials are not stored in Git
```

## M16: Add backup and restore drills

**Goal:** prove the system can recover.

Drills:

```text
restore annex metadata from Radicle
restore annex metadata from GitHub
restore content from archive
restore content from SeaweedFS hot pool
restore content from another peer
restore after one storage node disappears
restore after hot pool deletion
restore from tape/NAS/object
```

Add:

```text
docs/storage-fabric-runbook.md
docs/storage-fabric-restore-drills.md
```

Done when:

```text
restore is documented
restore is tested
restore does not depend on memory or vibes
```

## M17: Add lifecycle and cleanup policy

**Goal:** keep hot storage from becoming permanent junk storage.

Policies:

```text
scratch:
  can delete after job finishes

hot inputs:
  can delete when annex has safe copies elsewhere

hot outputs:
  cannot delete until archived

intermediate outputs:
  keep if expensive to recompute
  delete if cheap to recompute

final outputs:
  archive before drop

datasets:
  keep metadata forever
  content kept according to importance
```

Scripts:

```text
cluster-hot-report
cluster-hot-clean-safe
cluster-annex-expire-scratch
cluster-annex-protect-important
```

Done when:

```text
hot pool can be cleaned automatically
important data is protected
scratch does not fill the cluster forever
```

## M18: Add VS Code and workstation convenience

**Goal:** make this feel easy from any machine.

Add helper commands:

```text
cluster-data-open
cluster-data-preview
cluster-data-get-current
cluster-data-status
cluster-data-find
```

Workstation behavior:

```text
browse annex repo normally
see filenames even when content is absent
fetch content on demand
preview local content
open project in VS Code
stage active project to hot pool
```

Potential extras:

```text
file manager integration
README per project
manifest viewer
dataset status badges
```

Done when:

```text
from a workstation you can:
  find a dataset
  fetch it
  preview it
  stage it
  run compute elsewhere
  pull back outputs
```

## M19: Add compute-node integration

**Goal:** make compute nodes disposable but useful.

Compute node behavior:

```text
joins private Ygg
gets flake config
has annex client
has hot pool access
has local scratch
does not count as archive unless explicitly configured
can disappear safely
```

Job wrapper should prefer:

```text
1. local NVMe scratch
2. same-LAN SeaweedFS/hot pool
3. nearest annex peer over Ygg
4. archive/object remote
```

Done when:

```text
new compute node can join
pull active data
run job
publish outputs
leave without endangering data
```

## M20: Add multi-node failure behavior

**Goal:** define and test what survives what.

Failure cases:

```text
workstation offline:
  no issue

compute node offline:
  job may stop
  durable data safe

Seaweed volume node offline:
  hot pool degraded
  archive still source of truth

Radicle seed offline:
  GitHub/Gitea or other seed still works

archive node offline:
  hot workflows continue
  new durable copies may be delayed

private Ygg broken:
  content transfer stops
  system fails closed
```

Done when:

```text
each failure mode has:
  expected behavior
  operator warning
  recovery command
```

## M21: Add full deployment workflow

**Goal:** make rollout repeatable through the flake.

Add docs:

```text
docs/storage-fabric-rollout.md
```

Rollout phases:

```text
phase 1:
  one workstation
  one storage node
  one archive path

phase 2:
  add SeaweedFS hot pool

phase 3:
  add compute node

phase 4:
  add Radicle seed

phase 5:
  add second storage node

phase 6:
  add tape/object archive

phase 7:
  enable cleanup and health checks
```

Done when:

```text
Colmena/deploy-rs can deploy the storage fabric roles
new host only needs inventory role selection
```

## M22: Add complete operator docs

**Goal:** future-you can run it without rethinking it.

Docs:

```text
docs/storage-fabric.md
docs/storage-fabric-roadmap.md
docs/storage-fabric-runbook.md
docs/storage-fabric-restore-drills.md
docs/storage-fabric-security.md
docs/storage-fabric-failure-modes.md
docs/storage-fabric-command-reference.md
```

Done when docs answer:

```text
How do I add data?
How do I get data?
How do I stage a job?
How do I publish outputs?
How do I archive outputs?
How do I know data is safe?
How do I recover from a dead node?
How do I add a new storage node?
How do I prevent public transfers?
```

## M23: “Complete version” acceptance test

The full system is complete when this works:

```text
1. Fresh node joins private Ygg.
2. Node gets flake config.
3. Node sees Radicle/Git metadata.
4. Node sees annex file catalog.
5. Node fetches only requested data.
6. Node can stage active data into /hot.
7. Compute job runs from /hot or local scratch.
8. Outputs are annex-added.
9. Metadata syncs through Radicle/GitHub.
10. Outputs copy to archive.
11. Hot pool can evict data.
12. Another node can restore the output.
13. Public transfer paths are rejected.
14. One non-archive machine can disappear without data loss.
15. Monitoring reports whether copy policy is satisfied.
```

## Suggested milestone grouping

### Version 0.1: Design only

```text
M0
M1
M2
```

### Version 0.2: Basic annex fabric

```text
M3
M4
M5
```

### Version 0.3: Durable archive

```text
M6
M11
M16
```

### Version 0.4: SeaweedFS hot pool

```text
M7
M8
M9
```

### Version 0.5: Radicle-backed metadata

```text
M10
M12
```

### Version 0.6: Safe operations

```text
M13
M14
M15
M17
```

### Version 0.7: Workstation and compute convenience

```text
M18
M19
```

### Version 1.0: Complete private storage fabric

```text
M20
M21
M22
M23
```

## The core build order I would actually follow

```text
1. git-annex base
2. private-Ygg-only transfers
3. archive remote
4. SeaweedFS hot pool
5. job staging/publishing
6. Radicle metadata mirror
7. validation
8. observability
9. cleanup lifecycle
10. restore drills
```

That gets you useful behavior early while keeping the dangerous parts, like automated cleanup and cluster abstraction, behind validation and restore testing.
