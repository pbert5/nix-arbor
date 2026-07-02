# Registry MicroVM test debugging — 2026-06-23

Ran the three test layers described in
[`docs/cluster-ops/identity/registry/identity-registry-transport.md`](../docs/cluster-ops/identity/registry/identity-registry-transport.md#testing)
against the current registry rebuild (`rebuild-registry` branch) per
[`docs/cluster-ops/identity/registry/project-goals-and-roadmap.md`](../docs/cluster-ops/identity/registry/project-goals-and-roadmap.md).
Used the `/nixos` and `/dendritic` skills for repo conventions while
debugging.

## Pipeline run

1. `PYTHONPATH=tools/clusterctl python -m unittest discover -s tools/clusterctl/tests -v`
   — 9/9 pass. These tests mock `ipfs` calls, so they did not catch the bugs
   below.
2. `nix build .#checks.x86_64-linux.cluster-identity-registry-v1` — pass (runs
   the same Python tests inside the Nix sandbox).
3. `nix run ./experiments/cluster-identity-microvm#test` — failed on first run
   (exit 1), exercising the real `ipfs` binary against a live Kubo daemon.
   Debugged by adding temporary `exec >/shared/${role}.log 2>&1; set -x`
   tracing to the `registry-scenario` systemd service in
   `microvm-test.nix`, rebuilding, and inspecting
   `/tmp/cluster-identity-microvm/ipfs-publisher.log` after each run. Removed
   the tracing once the real fixes landed.

## Bugs found and fixed

Three bugs, surfaced one at a time as each was fixed and the next failure
appeared further down the `ipfs-publisher` scenario script:

1. **`tools/clusterctl/clusterctl/ipfs.py`** — `key_names()` called
   `ipfs key list --long`. The pinned Kubo version (0.40.1) only supports
   `-l` on `key list`/`key ls` (`--long` is not a recognized option and
   `key list` itself is deprecated in favor of `key ls`). Fixed to
   `ipfs key ls -l`.
2. **`experiments/cluster-identity-microvm/microvm-test.nix`** —
   `systemd.services.registry-scenario` ran with no `$HOME` set. Kubo's
   `ipfs` CLI errors (`$HOME is not defined`) even when only talking to a
   remote API socket via `--api`. Fixed with `export HOME=/root`, mirroring
   the existing pattern in
   `dendrites/system/dendrites/cluster-identity/cluster-identity.nix:85`.
3. Same file — the harness's own `ipfs name resolve --offline` and `ipfs cat`
   calls (used to verify the published IPNS head, not part of `clusterctl`)
   were missing `--api=/unix/run/ipfs.sock`, so they fell back to a
   nonexistent `~/.ipfs` repo (`no IPFS repo found`). Fixed by adding the
   flag to both calls, matching how `clusterctl` talks to the daemon.

Final diff: 2 files, ~4 lines.

## Verification

Re-ran all three layers after each fix. The MicroVM scenario was confirmed
passing multiple times via the `/tmp/cluster-identity-microvm/ipfs-success`
and `success` marker files, and once via a fully traced run that printed
`Registry validation passed` and exited 0 cleanly end-to-end (signed snapshot
published, IPNS resolved offline, `root.json` read back by CID and validated,
conflict-freezing assertions on the follower all held).

## Known issue (environment, not code)

Across several repeated runs, the final VM boot (`ipfs-publisher`) sometimes
did not have its qemu process exit promptly after a clean guest shutdown,
even though the scenario script had already written its success marker.
Documented in
[`identity-registry-transport.md`](../docs/cluster-ops/identity/registry/identity-registry-transport.md#known-issues)
so a future debugging session checks the marker files before assuming a
logic failure. Not pursued further since it reproduces inconsistently and is
orthogonal to the registry/clusterctl logic.

## Process issues hit while debugging, and how they were resolved

This took longer than it should have, mostly from self-inflicted process
mistakes rather than the underlying bugs being hard to find. Recording these
so the next pass through this harness (by me or anyone else) skips straight
to the fix.

1. **Stray `cd` silently broke a later run.** An earlier `cd
   experiments/cluster-identity-microvm` was never undone. A subsequent
   `nix run ./experiments/cluster-identity-microvm#test` resolved against
   the wrong base path and produced a single-line `error: getting status of
   "..."` — easy to miss in a long backgrounded log, and it looked like a
   silent no-op rather than an error. *Fix:* confirm `pwd` before any
   relative flake reference, or just use the absolute path.

2. **Overlapping test invocations caused resource contention that looked
   like a hang.** I kicked off a new backgrounded `nix run ...#test` while
   an earlier one's `qemu` process was still alive (it hadn't been confirmed
   dead). Both processes then competed for KVM/CPU against the same
   `/tmp/cluster-identity-microvm` shared directory, and the run that
   "looked stuck" was actually just starved. *Fix:* `ps aux | grep -E
   "qemu|microvm-test"` before starting a new run; kill anything left over
   and `rm -rf /tmp/cluster-identity-microvm` first.

3. **Exit code captured after a pipe was meaningless.** `nix run ... | tail
   -5; echo "EXIT: $?"` reports `tail`'s exit status, not the test's — this
   produced a false "EXIT: 0" once. *Fix:* capture `$?` immediately after
   the real command, before any pipe, or check the actual marker files
   instead of trusting a captured exit code at all.

4. **Misread "hang" vs. "already passed, teardown is slow."** The most
   time-consuming loop: assuming the test had failed/frozen because the
   qemu serial console stopped updating, when in fact
   `/tmp/cluster-identity-microvm/ipfs-success` already existed — the guest
   script had finished correctly and only the qemu process's shutdown was
   slow. Several minutes were spent waiting on background tasks and
   re-running instead of just checking the marker file immediately. *Fix:*
   when a MicroVM run appears to stall, check the marker files in the shared
   directory first, before re-running or killing anything.

5. **What worked well:** adding `exec >/shared/${role}.log 2>&1; set -x` to
   the `registry-scenario` service script, rebuilding, and reading the
   resulting log file in the shared directory was a fast, reliable way to
   see exactly which command inside a scenario step failed and why —
   far better than trying to parse the `quiet`-booted qemu console. Always
   `git diff` the experiment file afterward to confirm the instrumentation
   was fully reverted before calling a fix done.

These points are folded into the durable "Debugging Tips" section of
[`identity-registry-transport.md`](../docs/cluster-ops/identity/registry/identity-registry-transport.md#debugging-tips)
so they're discoverable without digging through this dated log.
