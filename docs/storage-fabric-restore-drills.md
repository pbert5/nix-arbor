# Storage Fabric Restore Drills

These drills are the M16 operator guide for proving that storage-fabric
recovery works before the archive automation is trusted.  The current fabric has
two service nodes:

| Host | Current role |
|------|--------------|
| `r640-0` | SeaweedFS master, volume, filer, annex storage, NAS archive staging, Radicle seed |
| `desktoptoodle` | SeaweedFS volume, filer, annex storage, tape archive, Radicle seed |

The hot pool is disposable.  The recovery source of truth is the annex metadata
repo plus enough content copies in annex storage and archive remotes.

## Before each drill

Record the starting state:

```bash
fabric-status
cluster-annex fsck-important
git -C /srv/annex/cluster-data annex sync
git -C /srv/annex/cluster-data annex info --fast
```

Pick a small test dataset and keep its path in the evidence notes:

```bash
cd /srv/annex/cluster-data
mkdir -p drills/restore-smoke
date -Is > drills/restore-smoke/sample.txt
git annex add drills/restore-smoke/sample.txt
git commit -m "restore drill sample"
git annex sync
cluster-annex archive drills/restore-smoke/sample.txt
git annex remotes
```

## Drill A: metadata clone from Radicle

Goal: prove that a fresh host can recover the annex tracking graph without
copying file content through Radicle.

```bash
rad clone rad:<cluster-data-repo-id> /tmp/cluster-data-restore
git -C /tmp/cluster-data-restore annex init "$(hostname)-restore-drill"
git -C /tmp/cluster-data-restore annex sync
git -C /tmp/cluster-data-restore annex whereis drills/restore-smoke/sample.txt
```

Success criteria:

- Git history is present.
- annex metadata is present.
- `whereis` lists storage or archive remotes for the test key.
- Radicle is not listed as a content-bearing annex remote.

## Drill B: metadata clone from GitHub

Goal: prove that the public Git mirror can recover metadata while content still
comes from private or archive remotes.

```bash
git clone https://github.com/<org>/cluster-data /tmp/cluster-data-github-restore
git -C /tmp/cluster-data-github-restore annex init "$(hostname)-github-restore-drill"
git -C /tmp/cluster-data-github-restore annex sync
git -C /tmp/cluster-data-github-restore annex whereis drills/restore-smoke/sample.txt
```

Success criteria are the same as the Radicle drill.

## Drill C: restore content from a peer storage node

Goal: prove private Yggdrasil content transfer works between fabric peers.

```bash
cd /srv/annex/cluster-data
git annex drop drills/restore-smoke/sample.txt
git annex get drills/restore-smoke/sample.txt --auto
git annex fsck drills/restore-smoke/sample.txt
```

Success criteria:

- `git annex get` fetches from a `*-ygg` remote.
- `git annex fsck` validates the restored content.
- no public annex content remote is used.

## Drill D: restore from NAS archive

Run on a node that can reach the NAS archive remote, currently `r640-0`.
Replace `archive-nas` with the actual NAS remote name from `git annex remotes`
if the local repo uses a different name.

```bash
cd /srv/annex/cluster-data
git annex drop drills/restore-smoke/sample.txt
git annex get drills/restore-smoke/sample.txt --from=archive-nas
git annex fsck drills/restore-smoke/sample.txt
```

Success criteria:

- the content is restored from the NAS archive remote
- `git annex fsck` validates the file

## Drill E: restore from tape archive

Run on a node with the tape archive configured, currently `desktoptoodle`.
Replace `archive-tape` with the actual tape remote name from `git annex remotes`
if the local repo uses a different name.

```bash
cd /srv/annex/cluster-data
git annex drop drills/restore-smoke/sample.txt
git annex get drills/restore-smoke/sample.txt --from=archive-tape
git annex fsck drills/restore-smoke/sample.txt
```

Success criteria:

- the operator can identify and load the required tape
- the content is restored from the tape archive remote
- `git annex fsck` validates the file

If the tape workflow needs manual media handling, record the manual step in the
drill evidence rather than hiding it in the command transcript.

## Drill F: hot pool rebuild

Goal: prove `/hot` can be treated as cache.

```bash
systemctl restart seaweedfs-hot-mount
cluster-annex get-active restore-smoke
find /hot -maxdepth 3 -type f | sort
```

Success criteria:

- the automount comes back
- project data can be staged from annex into the hot pool
- losing `/hot` does not remove annex metadata or archive copies

## Drill G: service-node loss tabletop

Do this as a tabletop before intentionally disabling a live storage node.

For loss of `desktoptoodle`:

- `r640-0` remains the SeaweedFS master.
- annex metadata remains available from Radicle/GitHub.
- NAS archive staging remains available on `r640-0`.
- tape restores wait until `desktoptoodle` or a replacement tape node returns.

For loss of `r640-0`:

- SeaweedFS loses the current master.
- annex metadata remains available from Radicle/GitHub.
- `desktoptoodle` still has annex storage and tape archive.
- NAS archive staging waits until `r640-0` or a replacement NAS node returns.

Current design note: `r640-0` is intentionally the only SeaweedFS master.  A
future failover milestone should document and test master replacement before
operators rely on automatic hot-pool continuity after `r640-0` loss.

## Evidence to keep

For each completed drill, save:

- date and operator
- host where the drill was run
- test annex key or path
- starting `fabric-status`
- restore command transcript
- final `git annex whereis` and `git annex fsck` result
- any manual archive media handling

Store drill evidence outside the hot pool, preferably in the annex metadata repo
under `manifests/restore-drills/` after removing any secrets or machine-local
paths that should not be shared.

Do not use forced drops during routine drills.  If `git annex drop` refuses,
fix the copy policy or choose a test key that already has enough verified
copies.
