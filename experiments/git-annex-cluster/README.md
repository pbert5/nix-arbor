# git-annex cluster experiment

> **Status:** experimental — not wired into the main flake.
> Lives under `experiments/` until behaviour is proven stable.

## Purpose

Test whether git-annex's built-in cluster feature improves metadata sync
over Radicle-backed remotes compared to plain per-host SSH remotes.

The main fabric uses normal git-annex remotes with preferred-content rules.
This experiment probes whether the cluster abstraction is worth adding on top.

## What this experiment covers

- Running multiple annex-storage nodes as a named cluster
- Routing content requests through the cluster rather than individual remotes
- Observing whether Radicle metadata sync stays clean with cluster-level tracking
- Verifying private-Ygg-only transfer policy still holds with cluster routing
- Drop-safety behaviour when one cluster node is offline

## What this experiment does NOT do

- Replace the stable fabric in the main flake
- Relax the private-overlay transfer policy
- Introduce new transport dependencies

## Test topology

```text
workstation (annex-client)
  ↕ SSH over Ygg
storage-0 (annex-storage, cluster member)
  ↕ SSH over Ygg
storage-1 (annex-storage, cluster member)
  ↕ Radicle over Ygg
metadata-mirror (radicle-seed)
```

## Files

| File | Purpose |
|------|---------|
| `README.md` | This file |
| `test-plan.md` | Step-by-step test procedure |

## Promotion criteria

Promote to mainline only if all of the following hold:

1. Cluster routing works better than individual remote selection
2. Failure states are visible, not silently swallowed
3. Radicle metadata sync does not become entangled with content transfer
4. Private-Ygg-only policy is not weakened
5. Normal non-cluster annex remotes continue to work alongside cluster remotes
