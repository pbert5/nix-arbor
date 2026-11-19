# Six workstreams: evidence inventory, 2026-11-17 UTC

This is a point-in-time inventory of six Codex chats on the same remote environment. It records source and test evidence, not authorization to deploy or merge. Local paths below identify preserved worktrees; they are not public artifact URLs. The six chat IDs are source identifiers, not links. Git remote main was verified at `3e557af25220a19f09f65b32914dd6f233a5e8c4`; the GitHub API was rate-limited, so recorded PR status may have changed.

| Workstream | Chat ID | Frontier |
| --- | --- | --- |
| Existing-root pairing | `01a1eb9a-0e3c-72d3-a239-a41aca4a9541` | Component checks passed; final combination and end-to-end pairing remain unproved. |
| Portable shell | `01a1eb97-9290-74b2-ac21-33a7a5e5fcbe` | Local prototype and Linux timing; macOS and final integration unverified. |
| Node admin TUI | `01a1eb84-37a7-7222-9295-a2ca68a7a064` | Latest integrated VM failed after committing a KV version. |
| Fastfetch | `01a1eb89-1d63-7e70-936a-5f7830f38d5f` | Local main contains the follow-up; ARM and activation unverified. |
| SSH routes | `01a1eb8d-5097-7a01-a229-e3f2fc7be773` | PR #9 recorded open; route compilation uses declared topology. |
| Raspberry Pi image | `01a1ea91-0ea0-7b62-a9b3-81d24dbb5a33` | Unpersonalized image and recorded offline inspection exist; review and physical boot remain. |

## Existing-root parent pairing

The design uses a parent-generated Magic Wormhole code, mutual approval and a signed parent relationship between existing Registry identities. The root worktree `.worktrees/existing-root-pair`, branch `agent/astra/existing-root-pair`, is clean at `d1041634f3fec8981e647f4c3b5e7bf898524af8`. The Registry worktree of the same name and branch is clean at `8fabfd72cafe562a263afbf9c09ac10aeba26c97`. The separate Registry `pair-acceptance` worktree is at `02ac42519c0a2cfe05e04ec2772c28d588b66f78` with a modified `tests/existing-root-pair.py`; preserve it. These are local work, with publication not established here.

The recorded component x86_64 flake check passed (`/tmp/arbor-pair-full-component-nix.log`); aarch64 was omitted. The exact final root/component combination and full end-to-end operation have not been established, and no live pairing is claimed. Next, reconcile the acceptance work with both exact heads, review and run the final combined test before considering any live action.

## Pairing versus private Ygg transport

Parent pairing establishes a signed, non-delegating Registry relationship. The separate private Ygg experiment supplies transport and does not itself establish Registry authority. Its local root branch `agent/registry/ygg-pair-sol62-20261117` at `119068522a7957e52d64d0b2165477c2eb9a0be3` and local component at `54778449db819fa921903f0e6c7200f0cac57780` were independently reviewed. Recorded evidence includes an isolated real-daemon two-guest VM and exact host closure builds using the configured cache. The component successor remains local-only in the recorded handoff; publication and a remote root pin require separate work. Registry main is pinned at `6147dd3a40c1787d1385d23617884499aeb5302d`; transport repair, the independent [Registry draft PR #7](https://github.com/pbert5/arbor-registry/pull/7), and parent pairing are distinct.

The handoff records [root PR #79](https://github.com/pbert5/nix-arbor/pull/79) as merged at `1f8cc6b1e2db8ce761be365ab26153cfae999639`; API readback was rate-limited. The experiment did not enable the managed provider or a Registry overlay listener, or demonstrate live raw convergence. Actual identities, network access and Registry state, the eVolver SSH baseline, and current activation and rollback evidence remain gates. Next, verify publication and pins and repeat relevant checks on any new candidate before seeking separate live authorization.

## Portable shell

The AshZsh worktree `.worktrees/ashzsh-portable-shell`, branch `agent/astra/portable-shell`, is clean at local head `73049e32fe54b21c1f43900756be7b74d5d9551f`; final publication and a root pin are not established. The design targets a copied Unix shell bundle with Zsh and no sudo or Nix requirement. Five warm runs on this Linux machine reported a 31 ms median portable prompt versus 780 ms for the installed login shell with its banner disabled. The portable profile loads fewer integrations and defers completion until first Tab, so these are different startup workloads.

No macOS execution, final full review or root integration has been established. Next, test on macOS and representative Unix environments, complete review, and decide whether to pin the reviewed component.

## Node admin TUI

The local worktree `.worktrees/node-admin-tui`, branch `agent/design/node-admin-tui`, holds the design and plan at `8c53e3c23ff839d0576d299b38926dab7f33019f`. Root integration `.worktrees/node-admin-integration`, branch `agent/astra/node-admin-integration`, is at `b6259a2be0f00deb7c94dc9eb8f715a2dd3955b1` with staged and unstaged changes and an untracked guide. Manager `.worktrees/node-admin-manager`, branch `agent/astra/node-admin-manager`, is at `fdb92e59522cc788eb86e26364562cacbae8be83` with a staged test and untracked cache directories. Preserve all of these; publication and deployment are not established.

Earlier chat progress reported successful fixture rotation and application use. The later `/tmp/arbor-node-admin-operator.log` records a failed consumer VM: KV version 2 was committed, but provider retrieved and materialized versions were `unknown`, and expected application-version markers were absent. This later failure limits the integration claim. Next, diagnose the provider/materialization frontier on the preserved work and rerun the exact end-to-end test, then review the resulting heads.

## Fastfetch

Root local main at `568df878e07ccaf381679d50d5a4ea426ab99dbb` contains service-status work `f40ee0189576eb6f68c738b4ed5eb8fb8a3917a2` and generation/elapsed-time follow-up `88831cbc50fa5c344ae77de09beb2182bda6ae8f`. The cached `origin/main` was `3e557af25220a19f09f65b32914dd6f233a5e8c4`, an ancestor of local main; live remote main matched that cached ref. The service-status commit is an ancestor of remote main; the follow-up is only established locally at this snapshot.

The chat reports fixture/banner checks and x86_64 flake validation passing. ARM validation and live activation are unverified. Next, verify current remote ancestry, review and publish through the normal process if desired, then validate ARM and activation separately.

## SSH routes

The clean flake-devbox worktree `.worktrees/cssh-native-routes`, branch `agent/astra/cssh-native-routes`, is at `ad89ed40b1f07bd1b65d91554e6e409b22189420`. [Issue #8](https://github.com/pbert5/flake-devbox/issues/8) and [PR #9](https://github.com/pbert5/flake-devbox/pull/9) were reported published; current API status could not be fetched. The compiler generates OpenSSH routes from declared links, not dynamic discovery or reachability. Links changing require route regeneration.

The chat reports 41 focused tests and a real loopback two-bastion SSH/SCP/Git test passing. It also reports broader flake failures on both base and head; recorded CI includes stale `src/tools/flake-mcp` paths, skipped Nix and other baseline failures. The chat originally reported CI still running, so the later failure status is a recorded snapshot, not a fresh readback. Independent review approved the exact head in the chat. Next, inspect the current PR and CI, distinguish baseline failures, and resolve remaining integration gates.

## Raspberry Pi image

The root takeover worktree `.worktrees/raspberry-evolver-takeover`, branch `agent/takeover/raspberry-evolver`, is at `0030603c1723ff88823e0f5f9f96831420eaea89` with a modified `docs/raspberry-evolver.md`; preserve it. No cached remote branch contains this head. [Tracker #61](https://github.com/pbert5/nix-arbor/issues/61) and earlier [PR #66](https://github.com/pbert5/nix-arbor/pull/66) and [PR #67](https://github.com/pbert5/nix-arbor/pull/67) do not establish readiness of this final head.

A local unpersonalized image and manifest exist outside the repository. The recorded native assembly completed in 347.98 seconds after a quota interruption; this timing is reported rather than independently reproduced. The image size is **4,588,568,576 bytes** and its SHA-256 is `aa4b1dc7783e2d8c4455a750b18313bfee1fa06904099be4173d24c6633d6cbc`; both were checked against the local file and manifest. No image was executed, mounted or rebuilt for this inventory. Recorded offline inspection metadata for this exact image reports boot files, identity locations and simulated partition checks. Those records do not establish final review or physical boot. Next, independently review the artifact inspection and exact head, reconcile the guide, and plan a separately authorized physical boot test.

## GitHub readback, 2026-11-19 UTC

- Source staging: [Nix Arbor #79](https://github.com/pbert5/nix-arbor/pull/79) merged as `1f8cc6b1e2db8ce761be365ab26153cfae999639`. [#80](https://github.com/pbert5/nix-arbor/pull/80) merged as `05108a929462313dfa4090ca366626cc16901cf6` with isolated canaries and an eVolver rollback runbook. These merges do not establish live private-Ygg activation. [Live bootstrap #12](https://github.com/pbert5/nix-arbor/issues/12) remains open. Verify the runbook baseline against current eVolver state before relying on it.
- Signed identity pairing: [Registry #11](https://github.com/pbert5/arbor-registry/pull/11) at `9a0cbda8` and [Nix Arbor #82](https://github.com/pbert5/nix-arbor/pull/82) at `78cebc11` are now published as open drafts, separate from the Ygg staging. PR publication is not evidence of live pairing.

## Evidence limits

The six named transcript files, local worktree states, pairing handoffs, TUI log and Pi artifact metadata were inspected. Private transcript text and credentials are intentionally omitted. The source chats include progress reports and do not all end in a terminal handoff; later local evidence takes precedence where identified. Test suites were not rerun for this documentation inventory. Paths under `/tmp` and local worktrees are ephemeral, while commit IDs and issue/PR links identify durable source where published.
