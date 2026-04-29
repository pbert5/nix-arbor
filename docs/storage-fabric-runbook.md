# Storage Fabric Runbook

Operator procedures for the cluster data fabric.  See
[storage-fabric.md](./storage-fabric.md) for the architecture overview,
[storage-fabric-security.md](./storage-fabric-security.md) for hardening, and
[storage-fabric-restore-drills.md](./storage-fabric-restore-drills.md) for
scheduled restore drills.

---

## Initial setup

### 1. Enroll a host in the fabric

Add the appropriate roles to the host's inventory entry:

```nix
# inventory/hosts.nix
my-storage-node = {
  roles = [ "annex-storage" "seaweed-volume" "archive-node" ];
  networks = [ "privateYggdrasil" ];
  dendrites = [ "base" "storage" "storage/git-annex" "storage/seaweedfs-hot" "storage/archive" ];
  org.storage.annex = {
    group = "archive";
    archive.nas.enable = true;
    archive.nas.path = "/srv/annex/archive/nas";
  };
};
```

### 2. Initialize the annex repo on a new host

After deploying the configuration:

```bash
cluster-annex init
```

This runs `git annex init`, sets `numcopies`, and registers the host's group.

### 3. Add a peer remote

```bash
git -C /srv/annex/cluster-data remote add storage-1 ssh://storage-1-ygg/srv/annex/cluster-data
git -C /srv/annex/cluster-data annex sync
```

### 4. Verify transfers are Ygg-only

```bash
git -C /srv/annex/cluster-data annex remotes
# All remote URLs must use *-ygg hostnames
```

---

## Daily operations

### Add data

```bash
git annex add <path>
git annex sync
```

### Stage project for hot pool

```bash
cluster-annex get-active <project>
```

Files are fetched into `/srv/annex/cluster-data/projects/<project>/` and
symlinked for use.

### Stage compute job inputs

```bash
cluster-annex stage-job <project> <job-id>
```

### Publish job outputs

```bash
cluster-annex publish-output <job-id>
```

This annex-adds everything under `outputs/<job-id>/` and syncs metadata.

### Archive important data

```bash
cluster-annex archive outputs/<job-id>/
```

### Safe drop from hot pool

```bash
cluster-annex drop-safe <path>
```

Will refuse to drop if `numcopies` would be violated.

### Check copy health

```bash
cluster-annex whereis <path>
cluster-annex fsck-important
```

---

## Restore procedures

Use the focused restore drill guide for scheduled proof runs:
[storage-fabric-restore-drills.md](./storage-fabric-restore-drills.md).

### Restore from archive (NAS)

Replace `archive-nas` with the actual NAS remote name from `git annex remotes`
if this repo uses a host-specific name.

```bash
git -C /srv/annex/cluster-data annex get <path> --from=archive-nas
```

### Restore from archive (tape)

Replace `archive-tape` with the actual tape remote name from `git annex remotes`
if this repo uses a host-specific name.

```bash
git -C /srv/annex/cluster-data annex get <path> --from=archive-tape
```

### Restore after storage node loss

1. Confirm remaining copies are sufficient:
   ```bash
   cluster-annex whereis <path>
   ```
2. Fetch from available remotes:
   ```bash
   git annex get <path> --auto
   ```
3. Re-replicate to a replacement node once it is enrolled.

### Restore annex metadata from Radicle

```bash
rad clone rad:<repo-id> /srv/annex/cluster-data
git -C /srv/annex/cluster-data annex init "$(hostname)-restored"
git -C /srv/annex/cluster-data annex sync
```

### Restore annex metadata from GitHub

```bash
git clone https://github.com/<org>/cluster-data /srv/annex/cluster-data
git -C /srv/annex/cluster-data annex init "$(hostname)-restored"
git -C /srv/annex/cluster-data annex sync
```

---

## SeaweedFS hot pool

### Check master status

```bash
weed shell -master=<ygg-addr>:9333 <<< "volume.list"
```

### Add a volume server manually

Volume servers self-register on startup.  Confirm registration:

```bash
weed shell -master=<ygg-addr>:9333 <<< "volume.list" | grep <new-host>
```

### Mount the hot pool on a compute node

The `seaweedfs-hot` filer leaf manages the `/hot` FUSE mount via systemd.
If the mount is absent after deployment:

```bash
systemctl start seaweedfs-filer
systemctl restart seaweedfs-hot-mount
systemctl status seaweedfs-hot-mount
```

---

## Radicle

### Check seed status

```bash
rad node status
rad node routing
```

### Force metadata sync

```bash
rad sync --fetch <repo-id>
```

### Verify no content transfer via Radicle

```bash
git -C /srv/annex/cluster-data annex remotes
# Radicle remote should appear only as a git remote, never as an annex remote
git -C /srv/annex/cluster-data annex info --fast | grep radicle
# Should show 0 known annex keys
```

---

## Validation

### Run flake check

```bash
nix flake check
```

Storage fabric checks catch:

- Storage roles without private Ygg enrollment
- `archive-node` without a backend
- archive backend facts, such as NAS paths, tape devices, and object endpoints
- `radicle-seed` without private Ygg
- public-looking annex content remotes
- SeaweedFS replication settings that need more `seaweed-volume` hosts
- SeaweedFS hot-pool paths and required master/volume/filer roles
- accidental multiple-master SeaweedFS inventory while the fabric is single-master

### Manually validate fabric config

```bash
nix eval .#inventory.storageFabric --json | jq .
```

### Verify live hardening

```bash
systemctl show seaweedfs-volume -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges
systemctl show seaweedfs-filer -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges
```

---

## Troubleshooting

### Annex transfer fails

1. Confirm SSH works over Ygg: `ssh annex@storage-0-ygg echo ok`
2. Check Ygg peer status: `yggdrasilctl getPeers`
3. Confirm remote URL uses `*-ygg`: `git annex remotes`
4. Check `numcopies`: `git annex numcopies`

### SeaweedFS volume not joining

1. Check master is listening: `ss -tlnp | grep 9333` (on Ygg interface)
2. Confirm volume service is running: `systemctl status seaweedfs-volume`
3. Check firewall: SeaweedFS ports must be open on the `ygg0` interface

### Hot pool mount missing

```bash
systemctl status seaweedfs-hot-mount
journalctl -u seaweedfs-filer -n 50
journalctl -u seaweedfs-hot-mount -n 50
```

### Radicle node not reachable from peers

1. Confirm Ygg address is reachable: `ping6 <ygg-addr>`
2. Check radicle port is open on ygg0: `ss -tlnp | grep 8776`
3. Check `rad node status` on both sides
