# Storage Fabric Restore Drills

These drills are the operator proof that the storage fabric can recover real
content instead of merely sounding emotionally supportive about it.

The current fabric has two service nodes:

| Host | Current role |
|---|---|
| `r640-0` | SeaweedFS master, volume, filer, annex storage, NAS archive staging, Radicle seed |
| `desktoptoodle` | SeaweedFS volume, filer, annex storage, Radicle seed |

The hot pool is disposable. The recovery source of truth is the annex metadata
repo plus enough surviving content copies in annex storage and archive remotes.

## Before each drill

Record the starting state:

```bash
fabric-status
cluster-annex fsck-important
git -C /srv/annex/cluster-data annex sync
git -C /srv/annex/cluster-data annex info --fast
```

Pick a small test dataset and make sure it is archived before using it in the
drill evidence.

```bash
cd /srv/annex/cluster-data
mkdir -p projects/restore-smoke
date -Is > projects/restore-smoke/sample.txt
git annex add projects/restore-smoke/sample.txt
git commit -m "restore drill sample"
git annex sync
cluster-annex archive projects/restore-smoke/sample.txt
git annex remotes
```

## Drill A: metadata clone from Radicle

Goal: recover annex metadata without using Radicle as a content transport.

```bash
rad clone rad:<cluster-data-repo-id> /tmp/cluster-data-restore
git -C /tmp/cluster-data-restore annex init "$(hostname)-restore-drill"
git -C /tmp/cluster-data-restore annex sync
git -C /tmp/cluster-data-restore annex whereis projects/restore-smoke/sample.txt
```

Success criteria:

- Git history is present.
- annex metadata is present.
- `whereis` lists content-bearing remotes for the sample key.
- Radicle is not acting as a content-bearing annex remote.

## Drill B: metadata clone from GitHub

Goal: recover metadata from a public Git mirror while keeping content on the
private or archive paths.

```bash
git clone https://github.com/<org>/cluster-data /tmp/cluster-data-github-restore
git -C /tmp/cluster-data-github-restore annex init "$(hostname)-github-restore-drill"
git -C /tmp/cluster-data-github-restore annex sync
git -C /tmp/cluster-data-github-restore annex whereis projects/restore-smoke/sample.txt
```

Success criteria are the same as the Radicle drill.

## Drill C: restore content from a peer storage node

Goal: prove private Yggdrasil content transfer between peers.

```bash
cd /srv/annex/cluster-data
git annex drop projects/restore-smoke/sample.txt
git annex get projects/restore-smoke/sample.txt --auto
git annex fsck projects/restore-smoke/sample.txt
```

Success criteria:

- `git annex get` restores from a private peer
- the transfer path is the Ygg alias, not a public endpoint
- `git annex fsck` validates the restored file

## Drill D: restore from NAS archive

Run on a host that can reach the NAS archive, currently `r640-0`.

```bash
cd /srv/annex/cluster-data
git annex drop projects/restore-smoke/sample.txt
git annex get projects/restore-smoke/sample.txt --from=archive-nas
git annex fsck projects/restore-smoke/sample.txt
```

Replace `archive-nas` with the actual remote name if your repo uses a different
one.

## Drill E: restore from tape archive

Status: planned, not currently active in the main inventory.

No active host currently selects the tape-library dendrite, enables the tape
archive backend, or attaches the `fossilsafe` fruit. Keep this drill as the
acceptance shape for the future tape archive promotion, but do not count it as
implemented evidence until a host explicitly declares the tape archive path.

```bash
cd /srv/annex/cluster-data
git annex drop projects/restore-smoke/sample.txt
git annex get projects/restore-smoke/sample.txt --from=archive-tape
git annex fsck projects/restore-smoke/sample.txt
```

Replace `archive-tape` with the actual remote name if needed.

If tape recovery requires manual media handling, record that step explicitly in
the drill evidence.

## Drill F: hot-pool rebuild

Goal: prove `/hot` is cache and can be rebuilt from durable sources.

```bash
systemctl restart seaweedfs-hot-mount
cluster-annex stage restore-smoke
find /hot -maxdepth 3 -type f | sort
```

Success criteria:

- the mount returns
- staged data is rebuilt from annex-managed content
- losing `/hot` does not remove metadata or archive copies

## Drill G: service-node loss tabletop

Do this as a tabletop before intentionally disabling a live service node.

### Loss of `desktoptoodle`

- `r640-0` remains the current SeaweedFS master
- annex metadata remains available via Radicle or GitHub
- NAS archive staging remains available on `r640-0`
- tape restore capacity is not part of the current main-fabric deployment

### Loss of `r640-0`

- SeaweedFS loses the current master
- annex metadata remains available via Radicle or GitHub
- `desktoptoodle` still has annex storage and SeaweedFS volume/filer capacity
- NAS archive staging waits until `r640-0` or a replacement NAS node returns

## Evidence to keep

For each completed drill, store:

- date and operator
- host where the drill ran
- test path or annex key
- starting `fabric-status`
- restore command transcript
- final `git annex whereis` and `git annex fsck` result
- manual archive media handling, if any

Store evidence outside `/hot`, ideally under `manifests/restore-drills/` in the
annex metadata repo after removing secrets or machine-local paths that should
not be shared.

## Safety notes

- do not use forced drops for routine drills
- if `git annex drop` refuses, fix copy policy or use a different test key
- do not treat a tabletop as evidence that a real restore path has been proven
