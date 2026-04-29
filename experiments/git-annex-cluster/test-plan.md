# git-annex cluster test plan

## Prerequisites

- At least two hosts enrolled in `privateYggdrasil` with `annex-storage` role
- `storage/git-annex` dendrite active on all test hosts
- `cluster-annex init` run on each host
- SSH key-based auth working between hosts using `*-ygg` aliases

## Phase 1: Normal remotes baseline

Establish a working baseline with plain SSH remotes before enabling the cluster
abstraction.

### Steps

1. On `storage-0`:
   ```bash
   cluster-annex init
   git -C /srv/annex/cluster-data remote add storage-1 ssh://storage-1-ygg/srv/annex/cluster-data
   git -C /srv/annex/cluster-data annex sync
   ```

2. From workstation:
   ```bash
   git clone ssh://storage-0-ygg/srv/annex/cluster-data ~/cluster-data
   cd ~/cluster-data
   git annex init "workstation"
   git annex group . workstation
   git annex wanted . present
   ```

3. Add a test file:
   ```bash
   echo "test payload" > datasets/test/hello.txt
   git annex add datasets/test/hello.txt
   git annex sync --content
   ```

4. Verify copies on both storage nodes:
   ```bash
   git annex whereis datasets/test/hello.txt
   # Expect: 2+ copies across storage-0 and storage-1
   ```

5. Drop from workstation, confirm safe:
   ```bash
   git annex drop datasets/test/hello.txt
   # Expect: success (numcopies satisfied by storage nodes)
   ```

6. Restore:
   ```bash
   git annex get datasets/test/hello.txt
   # Expect: restored from nearest storage node
   ```

**Baseline pass condition:** all six steps succeed without manual intervention.

## Phase 2: Enable annex cluster

Only proceed if Phase 1 passes.

### Steps

1. On `storage-0`, create a cluster:
   ```bash
   git -C /srv/annex/cluster-data annex initcluster "hot-cluster"
   git -C /srv/annex/cluster-data annex updatecluster --add storage-1
   ```

2. On workstation, add cluster as a remote:
   ```bash
   git -C ~/cluster-data remote add hot-cluster annex::hot-cluster
   git -C ~/cluster-data annex sync
   ```

3. Add a second test file through the cluster remote:
   ```bash
   echo "cluster payload" > datasets/test/cluster.txt
   git annex add datasets/test/cluster.txt
   git annex copy datasets/test/cluster.txt --to=hot-cluster
   git annex whereis datasets/test/cluster.txt
   ```

4. Take `storage-1` offline and verify the cluster remote still resolves:
   ```bash
   # (stop seaweedfs/annex services on storage-1 temporarily)
   git annex get datasets/test/cluster.txt --from=hot-cluster
   ```

5. Restore `storage-1` and re-sync:
   ```bash
   git annex sync --content
   git annex whereis datasets/test/cluster.txt
   # Expect: both storage nodes have copy again
   ```

**Cluster pass condition:** steps 3–5 succeed and failure mode in step 4 is
clearly reported (not silently dropped).

## Phase 3: Radicle metadata sync check

1. Ensure annex metadata branch syncs through Radicle for the cluster case.
2. Confirm the Radicle remote is NOT used for content transfer.
3. Kill the GitHub remote and verify metadata still propagates over Radicle.

**Radicle pass condition:** Git commits and annex tracking branch flow through
Radicle; content transfer never touches Radicle.

## Failure/abort criteria

Abort and do NOT promote if:

- Cluster abstraction hides which nodes have which copies
- `git annex whereis` output becomes less informative than with plain remotes
- A drop is allowed when only one cluster member holds the data
- Radicle becomes entangled with content transfer
- Any transfer touches a non-Ygg address
