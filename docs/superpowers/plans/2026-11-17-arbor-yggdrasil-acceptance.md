# Arbor Yggdrasil acceptance implementation plan

**Status** — Draft for review. The first workstream covers private peer admission and revocation. The sidecar, route recovery, and root integration build on that evidence.

**Goal** — Prove that accepted Arbor state controls real Yggdrasil traffic and that authorization changes converge without rebuilding a guest.

**Architecture** — Keep the NixOS VM checks with Yggdrasil Private, the reconciliation code and unit tests with Network Manager, and the component pins with Nix Arbor. Feed versioned accepted-state snapshots to the existing file watcher. Exercise the actual daemon, provider socket, Yggdrasil control socket, firewall, and IPv6 TCP service.

**Tech stack** — NixOS VM test driver, Yggdrasil and `yggdrasilctl`, systemd, and the Network Manager Python test suite.

**Design references** — [Networking architecture](../../networking-architecture.md) and [integration status](../../networking-status.md).

## Baseline

| Repository | Revision inspected | Existing evidence |
| --- | --- | --- |
| `pbert5/nix-arbor` | `fe12b653542eb2c4c35049fcceb4b0cb02074178` | Static composition policy and exported modules |
| `pbert5/yggdrasil-private` | `8543a1c0bac87553ba1ffb8c3d015303947f907d` | Evaluation of static key pinning and dynamic provider enablement |
| `pbert5/arbor-network-manager` | `2f551e4def84777d976cd243eb1a470f7e4bf611` | Route, authority, provider, and LAN VM checks |
| `pbert5/arbor-manager` | `a7a365dded1350e3c6ee55b7dcf70ac00f0c0a8d` | LAN ProxyJump VM harness with a recorded TCP/22 blocker |

Use these revisions to reproduce the baseline. Record the actual base SHA in each implementation issue. The live Registry watch feed, strict SSH execution, and live Tailscale acceptance remain separate follow-ups.

## 1. Establish the private link

**Owner** — Yggdrasil Private. Add `tests/private-ygg-vm.nix` and register `checks.<system>.private-ygg-vm` in `flake.nix`.

- [ ] Boot a static sender and target on an isolated VM LAN. Use deterministic test-only Ygg identities, disable multicast and external peers, and pin the expected keys. Bind a TCP responder on the target's Ygg IPv6 address and allow its port only on `ygg0`.
- [ ] Wait for the listener, verify the destination resolves to `ygg0` in the sender's kernel route table, check the peer's public key through the admin socket, and open a fresh TCP connection that returns the expected response. Check the port is closed on the underlay.
- [ ] Add a third guest with a different key on the same underlay. Confirm it can reach the transport listener and cannot establish an authorized peer session or reach the overlay responder. Confirm the authorized sender can still reach the responder after the negative probe.
- [ ] Run `nix build -L .#checks.x86_64-linux.private-ygg-vm` from Yggdrasil Private on a VM-capable Linux builder. Retain the check derivation and log with the tested SHA.

## 2. Prove dynamic admission, revocation, and restart

**Owners** — Network Manager owns control reconciliation and its regression tests in `arbor_network_manager/providers.py` and `tests/test_providers.py`. Yggdrasil Private owns `yggdrasil-private.nix` and a new `tests/private-ygg-dynamic-vm.nix` registered as `checks.<system>.private-ygg-dynamic-vm`. Use task 1's topology and share fixture setup where the settings match.

- [ ] First capture the real admin command responses from the pinned guest package. Verify the supported commands, JSON shape, URI normalization, exit status, and provider permissions. The existing adapter diffs reported peer URIs against the desired set, while the Nix module separately controls listener admission and overlay firewall sources. Exercise all three boundaries.
- [ ] Start with an empty accepted set and a healthy target service. Atomically replace the daemon's snapshot file with a new digest containing an accepted endpoint and the corresponding authorized route edge. Supply the test peer's pinned transport URI, overlay address, and endpoint generation using the existing adapter schema. Wait for the new digest, confirmed peer, and successful fresh TCP response.
- [ ] Replay the same snapshot. Verify the peer remains available and no duplicate add/remove operations occur. Publish revocation with a new digest and revoked endpoint or removed authority edge, as specified by the existing snapshot contract. Verify both an unreachable Arbor route and loss of packet access. Test a new TCP connection and an already-open stream, with the listener still healthy and the underlay still up.
- [ ] Make the provider reconcile only Arbor-managed peer state. Prove an empty desired set removes previously managed peers while preserving configured transport peers. Validate inputs before applying changes. Treat a failed or partial admin operation as unapplied and verify the next reconciliation converges. Use the VM evidence to decide where to enforce incoming admission or revocation if peer removal alone leaves access.
- [ ] Restart the provider, then Yggdrasil, while accepted and revoked peers coexist in the fixture. Confirm the authorized peer reconnects, the revoked peer stays blocked, and an old route binding fails revalidation when the accepted generation changes. Exercise an invalid snapshot during an authorized state and verify the daemon reports the error and retains the last accepted state.
- [ ] Run `nix build -L .#checks.x86_64-linux.route` in Network Manager. In Yggdrasil Private, use `--override-input arbor-network-manager` with the exact candidate revision or isolated checkout for integration, then run `nix build -L .#checks.x86_64-linux.private-ygg-dynamic-vm`. Re-run the static VM and the Yggdrasil Private `eval` check before handoff. Record the exact override used.

## 3. Prove private traffic across the public-peering sidecar

**Owner** — The component supplying the sidecar owns service changes. Yggdrasil Private owns `tests/private-ygg-sidecar-vm.nix` and `checks.<system>.private-ygg-sidecar-vm`. Identify and pin the supported sidecar module before marking this work ready. The private module currently references `yggdrasil-public-peering.service` by name.

- [ ] Put the private endpoints on separate VM networks with no direct transport path. Connect their sidecars across an isolated shared segment and attach a guest with public-plane reachability only. Verify the underlay topology and prove that disabling the sidecar breaks authorized private traffic while the private application stays healthy.
- [ ] Bring the sidecar back and assert that an authorized private TCP request succeeds. Verify the public-only guest can reach its public-plane neighbor and cannot reach the private service. Revoke an Arbor-managed peer and verify both the denied private connection and a continuing independent public-plane probe.
- [ ] Run `nix build -L .#checks.x86_64-linux.private-ygg-sidecar-vm` and re-run the direct dynamic VM check.

## 4. Add route recovery and promote

**Owners** — Network Manager owns route-health observations and solver behavior. Yggdrasil Private owns the packet-path fixture. Nix Arbor owns input promotion and published acceptance evidence.

- [ ] Add a VM check with independently interruptible preferred and backup paths. Prove both are eligible before the fault. Record the path selected by Arbor and independently verify packet delivery through the expected path using interface counters or an equivalent test assertion.
- [ ] Interrupt the preferred path, then both paths, then restore them. Verify backup selection and TCP delivery, followed by no usable route and no delivery during the full partition. Verify convergence after restoration and the preference declared in policy. Keep a revoked or unauthorized candidate in the fixture and verify it is never selected. Use the existing health and route contracts and extend them only where the checks demonstrate missing behavior.
- [ ] Give each VM assertion a bounded wait and report accepted digest, provider errors, peer state, kernel routes, and relevant unit logs on failure. Use fresh connections for recovery probes. Record the VM runner, exact SHAs, build commands, and outcomes.
- [ ] Obtain independent review of authority, firewall exposure, and restart behavior. Pin reviewed component revisions in Nix Arbor and rerun the published component checks at those revisions. Run `nix fmt` on changed Nix files and `nix flake check` in each changed flake, including the root. Update [networking status](../../networking-status.md) with the verified outcomes and remaining items.

## Workstream handoff

The first implementation issue covers tasks 1–2. Tasks 3 and 4 depend on the passing dynamic VM check. Before marking an issue `PROMPT_READY`, record its parent, base and integration target, assigned owner, component pins, shared VM resources, acceptance commands, reviewer, and stopping points. Implementation and testing use isolated guests and require no changes to a live tailnet or physical host. Merge and deployment follow the repository's approval rules. [Agent workflows](../../agent-workflows.md#prompt_ready-launch-contract)
