# Storage Fabric Validation

The storage fabric relies on `lib/validation/storage-fabric.nix` to reject
inventory states that are unsafe, contradictory, or too optimistic for the
current topology.

Run it through the normal repo checks:

```bash
nix flake check
```

You can also inspect the effective defaults directly:

```bash
nix eval .#inventory.storageFabric --json | jq .
```

## Site-wide policy checks

These checks look at the top-level `storageFabric` defaults.

- `storageFabric.transport.allowPublicContentTransfers` must stay `false` for
  the normal private-fabric posture.
- Seaweed hot-pool paths must be absolute:
  - `storageFabric.seaweedfs.hotPool.mountPoint`
  - `storageFabric.seaweedfs.hotPool.filerPath`
  - `storageFabric.seaweedfs.hotPool.volumePath`
- the Seaweed replication string must be a valid three-digit value such as
  `000` or `001`

## Seaweed topology checks

When `storageFabric.seaweedfs.hotPool.enable = true`, validation requires:

- at least one `seaweed-master` host
- exactly one declared `seaweed-master` host in the current design
- at least one `seaweed-volume` host
- at least one `seaweed-filer` host
- enough `seaweed-volume` hosts to satisfy the declared replication promise
- a `seaweed-s3` host if `s3.enable = true`
- at least one `seaweed-filer` host if `s3.enable = true`

For the current inventory, replication `001` means the fabric needs at least two
`seaweed-volume` hosts.

## Private-overlay enrollment checks

Hosts carrying storage-fabric service capabilities must be enrolled in the configured
private network, currently `privateYggdrasil`.

This applies to:

- `annex-storage`
- SeaweedFS capability flags
- `archive-node`
- `radicle-seed`

Validation also requires the private-overlay node entry to include a usable
address for service-role hosts, and a public key for `radicle-seed` hosts.

## Archive backend checks

Every `archive-node` must enable at least one backend under
`org.storage.annex.archive.*`.

Backend-specific checks include:

- NAS backend needs `path` or `mountPoint`
- tape backend needs `facts.storage.tape.devices.changer` and at least one drive
- object backend needs `endpoint`
- removable-disk backend needs `path`
- object endpoints must look private unless public content transfer is allowed

## Content-remote URL checks

Per-host declared annex remotes under `org.storage.annex.remotes` are checked so
that content does not quietly drift onto metadata-only or public-looking URLs.

Validation rejects remotes that look like:

- GitHub HTTPS or SSH Git URLs used as content remotes
- Radicle URLs used as content remotes
- non-private-looking endpoints when the private transfer policy is active

Private-looking endpoints currently include names containing markers such as:

- `-ygg`
- `.ygg`
- `.internal`
- `localhost`
- loopback addresses

## What validation does not do

Validation is intentionally static. It does not prove that:

- the remote host is alive right now
- the announced path is mounted correctly at runtime
- tape media is loaded
- archive content is healthy
- `/hot` is mounted

Use runtime checks such as `fabric-status`, `systemctl status`, `git annex
whereis`, and the restore drills for those.

## Typical failure messages to expect

Common failures include:

- hot pool enabled with no master, volume, or filer host
- replication requiring more volume hosts than inventory declares
- archive node enabled with no backend
- tape backend enabled with missing device facts
- object archive endpoint that looks public
- storage-role host missing from the private overlay inventory
- `radicle-seed` host missing its private key metadata
