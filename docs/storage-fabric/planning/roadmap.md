# Storage Fabric Roadmap

This page tracks the current storage-fabric milestone state and the next pieces
that still need promotion from “good idea” to “boringly operational”.

## Current milestone state

| Milestone | State | Notes |
|---|---|---|
| M0-M2 | implemented | design docs, inventory schema, and storage-fabric capability flags exist |
| M3-M5 | implemented | git-annex base, private-transfer policy, and cluster repo initialization exist |
| M6-M9 | implemented subset | archive support, SeaweedFS hot pool, `/hot` staging, and job helper commands exist |
| M10-M11 | implemented subset | Radicle seed wiring and metadata/content separation are modeled |
| M12 | planned | git-annex cluster-mode testing remains isolated under `experiments/` |
| M13 | implemented subset | `fabric-status` and the annex health timer exist |
| M14 | implemented subset | validation catches overlay enrollment, archive facts, public content remotes, and impossible replication promises |
| M15 | implemented subset | service sandboxing, private-transfer enforcement, annex SSH restrictions, and security docs exist |
| M16 | implemented subset | restore drill procedures exist; regular evidence collection still needs to become routine |
| M17-M23 | planned | lifecycle cleanup, workstation convenience, compute integration, failure-mode docs, rollout docs, broader acceptance tests |

## Current deployment shape

| Host | Current shape |
|---|---|
| `r640-0` | SeaweedFS master + volume + filer, annex storage, NAS archive, Radicle seed, observer |
| `desktoptoodle` | SeaweedFS volume + filer, annex storage, Radicle seed, observer |

Notes:

- the hot pool currently depends on `r640-0` as the only declared master
- replication `001` matches the two declared `seaweed-volume` hosts
- tape-specific archive automation is disabled on `desktoptoodle` for now

## Near-term order

1. keep running and recording restore drills until recovery is routine
2. finish the remaining secret-management path for future object or S3 archives
3. add more explicit lifecycle cleanup and failure-mode docs as the operator
   surface expands
4. document master failover only when a real design is ready to be tested

## Promotion boundaries

The built-in git-annex cluster experiment remains outside the main fabric. Keep
prototype work under `experiments/` until there is a deliberate promotion step.

That rule matters here because the storage fabric already has enough real moving
parts; mixing an experiment into the live path would be a spectacularly boring
way to create exciting outages.
