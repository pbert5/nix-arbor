# Storage Fabric Runbook

Use this page for practical operator work: initial enrollment, common daily
commands, and service checks. For fast command lookup, pair it with
[`reference/command-reference.md`](./reference/command-reference.md).

## Before changing anything

Run the standard repo validation first:

```bash
git status --short
nix flake check
```

If the change affects a newly created tracked file, remember that flake
evaluation only sees staged files.

## Enroll a host in the fabric

Add the storage-fabric capability flags and host overrides in
`inventory/hosts.nix`.

```nix
my-storage-node = {
  org.storage.annex.fabric = {
    storage = true;
    archive = true;
  };
  org.storage.seaweedfs.volume = true;
  networks = [ "privateYggdrasil" ];
  dendrites = [
    "base"
    "storage/git-annex"
    "storage/seaweedfs-hot"
    "storage/archive"
  ];
  org.storage.annex = {
    group = "archive";
    archive.nas = {
      enable = true;
      path = "/srv/annex/archive/nas";
    };
  };
};
```

Then rebuild the host and run `nix flake check` from the repo before switching.

## Initialize annex on a new host

After the host is deployed:

```bash
cluster-annex init
cluster-annex set-group archive
```

`cluster-annex init` initializes the repo if it does not already exist and sets
`numcopies` to the site default.

## Add peer remotes over Ygg

```bash
cluster-annex add-remote r640-0 r640-0-ygg
cluster-annex add-remote desktoptoodle desktoptoodle-ygg
cluster-annex sync
```

The helper builds `annex+ssh://<host-alias>/srv/annex/cluster-data` remotes.
Keep content remotes on the private overlay.

## Daily annex operations

### Add and sync content

```bash
git -C /srv/annex/cluster-data annex add <path>
cluster-annex sync
```

### See where content lives

```bash
cluster-annex whereis <path>
```

### Archive important content

```bash
cluster-annex archive outputs/<job-id>/
```

### Drop only when safe

```bash
cluster-annex drop-safe <path>
```

### Run a focused health check

```bash
cluster-annex fsck-important
fabric-status
```

## Stage active work into the hot pool

### Stage a project

```bash
cluster-annex stage <project>
```

This populates `/hot/projects/<project>` from annex-tracked content.

### Remove a staged project

```bash
cluster-annex unstage <project>
```

## Stage, publish, and clean a job

### Stage a compute job

```bash
cluster-annex job-stage <project> <job-id>
```

This creates `/hot/scratch/<job-id>/input` and `/hot/scratch/<job-id>/output`.

### Publish outputs back into annex

```bash
cluster-annex job-publish <job-id>
```

This copies output into `outputs/<job-id>/`, `annex add`s it, commits a local
metadata update, and syncs content and metadata.

### Clean hot staging after publish

```bash
cluster-annex job-clean <job-id>
```

## SeaweedFS checks

### Check service state

```bash
systemctl status seaweedfs-master --no-pager
systemctl status seaweedfs-volume --no-pager
systemctl status seaweedfs-filer --no-pager
systemctl status seaweedfs-hot-mount --no-pager
```

### Inspect the current volume map

```bash
weed shell -master=<ygg-addr>:9333 <<< "volume.list"
```

### Recover a missing hot mount

```bash
systemctl restart seaweedfs-filer
systemctl restart seaweedfs-hot-mount
mountpoint /hot
```

If `/hot` is gone but annex and archive copies are healthy, treat it as a cache
rebuild rather than a data-loss incident.

## Radicle checks

### Confirm the seed is up

```bash
systemctl status radicle-seed --no-pager
rad node status
rad node routing
```

### Force metadata sync

```bash
rad sync --fetch <repo-id>
```

### Confirm Radicle is metadata-only

```bash
git -C /srv/annex/cluster-data remote -v
git -C /srv/annex/cluster-data annex info --fast | grep radicle
```

The Radicle remote should be a Git remote only, not a content-bearing annex
remote.

## Restore pointers

For formal recovery exercises, use
[`restore-drills.md`](./restore-drills.md).

For tape-backed recovery work, use the tape hardware notes under
[`../../tape-library/hardware/README.md`](../../tape-library/hardware/README.md).

## Quick troubleshooting starters

- run `fabric-status`
- check `cluster-annex whereis <path>` for missing copies
- verify `git remote -v` and `git annex remotes` still use Ygg aliases
- inspect `systemctl status` for the relevant SeaweedFS or Radicle unit
- re-run `nix flake check` if the problem smells like inventory drift
