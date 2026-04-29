# Storage Fabric Roadmap

The storage fabric is being implemented as declarative inventory plus reusable
dendrites.  Prototype-only ideas stay in `experiments/` until explicitly
promoted.

## Current milestone state

| Milestone | State | Notes |
|-----------|-------|-------|
| M0-M2 | implemented | Design docs, inventory schema, and fabric roles exist. |
| M3-M5 | implemented | git-annex base, private-transfer policy, and cluster repo initialization are present. |
| M6-M9 | implemented subset | Archive, SeaweedFS hot pool, `/hot` staging, and job helper commands are available. |
| M10-M11 | implemented subset | Radicle seeding and metadata/content remote separation are modeled. |
| M12 | planned | git-annex cluster-mode testing belongs under `experiments/`. |
| M13 | implemented subset | `fabric-status` and daily annex health timer are present. |
| M14 | implemented subset | Inventory validation now catches private-overlay enrollment, archive facts, public content remotes, and impossible SeaweedFS replication promises. |
| M15 | implemented subset | SeaweedFS and Radicle service sandboxing, private-overlay enforcement, annex SSH restrictions, and security guide are present. Secret rotation and locked annex login shell remain planned. |
| M16 | implemented subset | Restore drill guide exists for metadata, peer content, NAS, tape, hot-pool rebuild, and service-node-loss tabletop. Drills still need real evidence from scheduled runs. |
| M17-M23 | planned | Lifecycle cleanup, workstation convenience, compute integration, failure-mode docs, rollout docs, command reference, and acceptance tests remain. |

## Near-term order

1. Run and record M16 restore drills until they are boring.
2. Add M17 lifecycle cleanup only after restore drills have evidence.
3. Continue M15 follow-up for credentials and any future S3/object archive secrets.
4. Add failure-mode and rollout docs as the operational surface grows.

## Current deployment shape

`r640-0` is the SeaweedFS master and a storage-fabric service node.  It owns
annex storage, SeaweedFS volume/filer, NAS archive staging, Radicle seed, and
observability roles.

`desktoptoodle` is now a peer storage-fabric service node without the
SeaweedFS master role.  It owns annex storage, SeaweedFS volume/filer, tape
archive, Radicle seed, and observability roles.

The hot pool currently uses SeaweedFS replication `001`, because inventory
declares two `seaweed-volume` hosts: `r640-0` and `desktoptoodle`.  Keep
`seaweed-master` on `r640-0` unless a later failover design promotes another
master.
