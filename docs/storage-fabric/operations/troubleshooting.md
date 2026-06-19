# Storage Fabric Troubleshooting

This page is the first-pass triage guide for the failure modes most likely to
show up in routine storage-fabric work.

## Start with these checks

```bash
fabric-status
nix flake check
git -C /srv/annex/cluster-data annex info --fast
git -C /srv/annex/cluster-data annex remotes
```

These usually tell you whether the problem is inventory drift, a missing copy, a
service outage, or a remote misconfiguration.

## Annex transfer fails

### Symptoms

- `git annex get` hangs or fails
- peer copies exist but are not fetched
- sync succeeds for Git metadata but content will not move

### Checks

1. verify Ygg SSH reachability:
   ```bash
   ssh annex@r640-0-ygg echo ok
   ```
2. inspect content remotes:
   ```bash
   git -C /srv/annex/cluster-data annex remotes
   git -C /srv/annex/cluster-data remote -v
   ```
3. inspect copy locations:
   ```bash
   cluster-annex whereis <path>
   ```
4. confirm Ygg is healthy:
   ```bash
   yggdrasilctl getPeers
   ```

### Common causes

- content remote points at a public or wrong hostname
- peer SSH keys or host keys drifted
- the file does not actually have enough surviving copies

## Annex repo not initialized

### Symptoms

- `fabric-status` reports that the annex repo is not initialized
- `/srv/annex/cluster-data/.git` is missing

### Recovery

```bash
cluster-annex init
cluster-annex set-group archive
cluster-annex add-remote <name> <host-alias>
cluster-annex sync
```

Use the correct preferred-content group for the host role instead of blindly
using `archive` everywhere.

## Files are lacking copies

### Symptoms

- `fabric-status` reports files with fewer than the configured copy count
- `git annex find --lackingcopies=1` returns results

### Checks

```bash
git -C /srv/annex/cluster-data annex find --lackingcopies=1
cluster-annex whereis <path>
```

### Recovery ideas

- sync to peers
- restore a missing archive copy
- avoid drops until the copy count is healthy again

## SeaweedFS volume not joining

### Checks

```bash
systemctl status seaweedfs-master --no-pager
systemctl status seaweedfs-volume --no-pager
weed shell -master=<ygg-addr>:9333 <<< "volume.list"
ss -tlnp | grep -E '(:9333|:19333|:8090|:18090)'
```

### Common causes

- master is down
- the volume host is not on the private overlay
- the firewall is exposing or blocking the wrong ports
- inventory replication promises do not match the declared volume hosts

## `/hot` is not mounted

### Checks

```bash
systemctl status seaweedfs-filer --no-pager
systemctl status seaweedfs-hot-mount --no-pager
mountpoint /hot
journalctl -u seaweedfs-filer -n 50 --no-pager
journalctl -u seaweedfs-hot-mount -n 50 --no-pager
```

### Recovery

```bash
systemctl restart seaweedfs-filer
systemctl restart seaweedfs-hot-mount
```

If annex and archive copies remain healthy, treat this as cache recovery.

## Radicle seed not starting

### Checks

```bash
systemctl status radicle-seed --no-pager
journalctl -u radicle-seed -n 50 --no-pager
rad node status
```

### Common causes

- `org.network.radicle.privateKeyFile` is not set on a `radicle-seed` host
- the key does not exist on disk yet
- Ygg bind address or firewall state is wrong

Remember that the service is keyed off the host role plus a private key path,
not only the site-wide defaults.

## Validation failures from `nix flake check`

### Likely messages and what they mean

- private transfer policy disabled: public content transfer was turned on
- no `seaweed-master`: hot pool enabled without a master host
- replication impossible: not enough `seaweed-volume` hosts for the declared
  replication string
- archive node missing backend: host claims `archive-node` but enables nothing
- tape backend missing facts: tape archive enabled without changer or drive facts
- object endpoint looks public: object archive points somewhere non-private

For the full grouped list, see [`../policy/validation.md`](../policy/validation.md).

## Tape archive issues

If the broken part involves media loading, LTFS mounts, or tape inventory, leave
this page and use the tape-library docs directly:

- [`../../tape-library/hardware/README.md`](../../tape-library/hardware/README.md)
- related notes under `docs/tape-library/`
