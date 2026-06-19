# Storage Fabric Security

This page records the security posture that is implemented for the storage
fabric today, plus the parts that remain explicitly planned.

## Primary boundary: private content transfer

The storage fabric is private by default.

- `storageFabric.transport.allowPublicContentTransfers = false` is the normal
  rule.
- annex content remotes are expected to use private Ygg aliases such as
  `*-ygg`.
- SeaweedFS ports are opened only on the Yggdrasil interface.
- archive object endpoints must look private unless the site policy is changed
  deliberately.
- Radicle binds to the private overlay when a seed host has a Ygg address.

Public Git remotes may still exist for normal Git metadata, but that does not
make them acceptable annex content remotes.

## Service isolation

Storage services run under dedicated service users rather than a shared root-ish
blob of vibes.

| Service | User | Main state path |
|---|---|---|
| annex repo operations | `annex` | `/srv/annex/cluster-data` |
| SeaweedFS master | `seaweedfs` | `/srv/seaweedfs/master` |
| SeaweedFS volumes | `seaweedfs` | `/srv/seaweedfs/volumes` |
| SeaweedFS filer | `seaweedfs` | `/srv/seaweedfs/filer` |
| Radicle seed | `radicle` | `/var/lib/radicle` |

### Current sandboxing

SeaweedFS services use conservative systemd sandboxing, including:

- `PrivateTmp = true`
- `ProtectSystem = "full"`
- `ProtectHome = true`
- `NoNewPrivileges = true`
- `RestrictRealtime = true`
- `RestrictSUIDSGID = true`
- `LockPersonality = true`
- native syscall architecture only
- limited socket families

Radicle is stricter and uses:

- `ProtectSystem = "strict"`
- `ReadWritePaths = [ "/var/lib/radicle" ]`
- `NoNewPrivileges = true`

## Annex SSH restrictions

The annex SSH surface is intentionally narrow.

- SSH keys come from inventory rather than manual snowflake edits.
- Ygg aliases are the expected hostnames for storage peers.
- `git-annex-shell -d /` is used as a forced command for restricted annex
  operations.
- agent forwarding, TCP forwarding, X11 forwarding, and TTY allocation are
  disabled for the annex account.

This keeps the annex account closer to a purpose-built transfer endpoint than a
normal interactive login.

## Archive backend boundary

Archive nodes must declare a real backend, and object-store endpoints must stay
private-looking unless the site policy deliberately changes. Tape access is
bounded by explicit tape manager selection and device facts when a host enables
that backend.

## Credentials and secrets

Secrets are not meant to live in inventory or docs.

Current posture:

- SeaweedFS S3 is disabled by default until credentials are modeled properly.
- future object-store or S3 credentials should be managed through the repo's
  secret path, not committed config.
- credential rotation docs remain planned work once those backends are live.

## Operator checks

After deployment, confirm that the live system still matches the policy:

```bash
nix flake check
systemctl show seaweedfs-master -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges
systemctl show seaweedfs-volume -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges
systemctl show seaweedfs-filer -p User -p ProtectHome -p ProtectSystem -p NoNewPrivileges
systemctl show radicle-seed -p User -p ProtectSystem -p NoNewPrivileges
ss -tlnp | grep -E '(:9333|:19333|:8090|:18090|:8888|:18888|:8333|:8776)'
```

On hosts that do not carry a given service, skip the corresponding check.

## Still planned

The current remaining security follow-up is small but important:

- model future object/S3 credentials through the repo's secret-management path
- add credential rotation notes once those backends are enabled
- consider an even tighter annex service-account login posture after confirming
  it does not break required operations
