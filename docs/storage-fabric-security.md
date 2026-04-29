# Storage Fabric Security

This document records the security posture that is implemented for the storage
fabric today, plus the parts that remain planned.  The storage fabric is private
by default: data content moves over the private Yggdrasil overlay, while public
networks may carry only ordinary Git metadata when an operator explicitly uses a
public Git remote.

## Current enforcement

The private-transfer rule is encoded in Nix:

- `storageFabric.transport.allowPublicContentTransfers = false` is the default.
- Inventory validation rejects public-looking annex and object archive content
  remotes.
- Annex SSH remotes are expected to use `*-ygg` host aliases.
- SeaweedFS master, volume, filer, S3, and gRPC companion ports are opened only
  on the configured private overlay interface.
- Radicle nodes bind to the private Yggdrasil address.

Run the normal flake validation before deployment:

```bash
nix flake check
```

## Service isolation

Storage services run under dedicated service users:

| Service | User | State path |
|---------|------|------------|
| git-annex fabric repo | `annex` | `/srv/annex/cluster-data` |
| SeaweedFS master | `seaweedfs` | `/srv/seaweedfs/master` |
| SeaweedFS volumes | `seaweedfs` | `/srv/seaweedfs/volumes` |
| SeaweedFS filer | `seaweedfs` | `/srv/seaweedfs/filer` |
| Radicle seed | `radicle` | `/var/lib/radicle` |

The SeaweedFS services currently use conservative systemd sandboxing:

- `PrivateTmp = true`
- `ProtectSystem = "full"`
- `ProtectHome = true`
- kernel tunable, module, log, and cgroup protection
- `NoNewPrivileges = true`
- `RestrictRealtime = true`
- `RestrictSUIDSGID = true`
- `LockPersonality = true`
- native syscall architecture only
- socket families limited to Unix, IPv4, and IPv6

`ProtectSystem = "full"` is intentional for SeaweedFS because its live state is
under `/srv`.  The service pre-start scripts create the exact state directories
with the `seaweedfs` owner before the daemon starts.

Radicle is stricter: it uses `ProtectSystem = "strict"` with
`ReadWritePaths = [ "/var/lib/radicle" ]`.

## Annex SSH access

The annex SSH leaf restricts the `annex` account for storage transfers:

- SSH keys come from host inventory, not ad-hoc local edits.
- Yggdrasil host aliases are generated for private peers.
- `ForceCommand git-annex-shell -d /` limits SSH sessions to annex protocol
  operations.
- agent forwarding, TCP forwarding, X11 forwarding, and TTY allocation are
  disabled for the annex account.

Operators should not add public annex content remotes unless the site policy is
changed deliberately and validation is updated with that risk in mind.

## Credentials

Secrets are not meant to live in inventory or docs.  The SeaweedFS S3 gateway is
currently disabled in inventory until credentials are modeled through the repo's
secret-management path.

Planned M15 follow-up:

- move any future object-store credentials into SOPS/age-managed secrets
- add credential rotation notes once S3 or object archives are enabled
- consider a locked login shell for the annex service account after confirming
  it does not interfere with service-managed annex operations

## Operator checks

After deployment, check that the live services are private-bound and sandboxed:

```bash
systemctl show seaweedfs-master -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges
systemctl show seaweedfs-volume -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges
systemctl show seaweedfs-filer -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges
ss -tlnp | grep -E '(:9333|:19333|:8080|:18090|:8888|:18888)'
```

On `desktoptoodle`, omit `seaweedfs-master` because `r640-0` is the only
SeaweedFS master in the current design.
