# Storage Fabric

The storage fabric is the repo's private, Yggdrasil-bound data plane for large
content. It combines `git-annex` for content identity and copy policy,
SeaweedFS for the disposable hot pool, archive backends for durable storage, and
Radicle or ordinary Git remotes for metadata replication.

This directory splits the fabric docs by topic so it is easier to jump straight
to the part you need instead of spelunking through one giant page.

## Read by task

| If you want to... | Read this |
|---|---|
| understand the overall design | [`architecture/overview.md`](./architecture/overview.md) |
| see how the major services fit together | [`architecture/components.md`](./architecture/components.md) |
| edit inventory, capability flags, or host overrides | [`architecture/inventory-and-roles.md`](./architecture/inventory-and-roles.md) |
| do setup or daily operator work | [`operations/runbook.md`](./operations/runbook.md) |
| look up commands quickly | [`operations/reference/command-reference.md`](./operations/reference/command-reference.md) |
| run recovery tests | [`operations/restore-drills.md`](./operations/restore-drills.md) |
| review security posture and boundaries | [`policy/security.md`](./policy/security.md) |
| understand what validation enforces | [`policy/validation.md`](./policy/validation.md) |
| check current milestone state | [`planning/roadmap.md`](./planning/roadmap.md) |

## Core rules

- `git-annex` is the durable source of truth for content identity and copy
  policy.
- SeaweedFS `/hot` is a working cache, not an authority.
- Archive backends are for long-term survival, not convenience staging.
- Annex content transfers stay on the private Yggdrasil overlay unless policy is
  deliberately changed.
- Radicle and public Git remotes carry metadata, not annex payloads.

## Current deployment at a glance

| Host | Current storage-fabric role mix |
|---|---|
| `r640-0` | annex storage, SeaweedFS master, SeaweedFS volume, SeaweedFS filer, NAS archive node, Radicle seed, observer |
| `desktoptoodle` | annex storage, SeaweedFS volume, SeaweedFS filer, Radicle seed, observer |

The current hot-pool replication target is `001`, which matches the two declared
`seaweed-volume` hosts above.

## Related docs

- Tape hardware notes live under
  [`docs/tape-library/hardware/README.md`](../tape-library/hardware/README.md) and
  [`docs/tape-library/README.md`](../tape-library/README.md).
- Cluster rollout, deployment, and fleet operator docs live under
  [`docs/cluster-ops/`](../cluster-ops/).
- The `git-annex` built-in cluster-mode experiment remains isolated under
  `experiments/git-annex-cluster/`; it is not part of the main fabric today.
