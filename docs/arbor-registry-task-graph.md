# Arbor Registry task graph

Lead-maintained queue for the extraction. States use the repository workflow:
`READY`, `IN_PROGRESS`, `BLOCKED`, `INTEGRATION`, `REVIEW`, `VALIDATION`,
`DONE`.

| ID | State | Dependencies | Owner / write set | Deliverable |
|---|---|---|---|---|
| REGISTRY-AUDIT | DONE | — | research | legacy classification and evidence |
| ARBOR-MANAGER-AUDIT | DONE | — | research | current API and source seam |
| SYSTEMD-VAULTD-RESEARCH | DONE | — | research | credential integration evidence |
| COLMENA-RESEARCH | DONE | — | research | backend contract and risks |
| GRAPH-MODEL | DONE | — | architecture | relationship and SCC invariants |
| COMPATIBILITY-MODEL | DONE | — | architecture | envelope/quarantine rules |
| ARCHITECTURE-SYNTHESIS | DONE | six discovery tasks | lead | frozen boundary in `docs/arbor-registry-architecture.md` |
| EXTRACT-ARBOR-REGISTRY | DONE | audit + synthesis | worker; `packages/arbor-registry` | standalone registry library/flake |
| REGISTRY-RECONCILIATION | DONE | extraction + graph + compatibility | worker scope | accepted/materialized state, quarantine and tests |
| MANAGER-SOURCE-ABSTRACTION | DONE | manager audit + synthesis | worker; `packages/arbor-manager` | pure source API, role removal, read-only metadata |
| SECRET-BOUNDARY-MODEL | DONE | audit + vault research | research | runtime-only identity/secret brief |
| MACHINE-RECORD-MODEL | DONE | manager audit + synthesis | research | normalized source/merge contract |
| NETWORK-INTERFACE-MODEL | DONE | graph + machine contract | research | provider-neutral runtime API |
| DEPLOYMENT-MODEL | DONE | graph + Colmena research | research | planner/backend contract |
| ROOT-REGISTRY-COMPOSITION | DONE | registry + manager outputs | lead; root flake | local component input and override wiring |
| REGISTRY-MACHINE-SOURCE | DONE | registry + manager + machine model | manager | pure digest-requiring snapshot adapter |
| MACHINE-SNAPSHOT-TOOLING | DONE | registry source | manager; `packages/arbor-manager` | inspect/export provenance and digest checks |
| OPENBAO-RUNTIME-IDENTITY | DONE | secret boundary + registry | registry; `packages/arbor-registry` | runtime identity generations and recovery boundary |
| ENROLLMENT-RECOVERY-LIFECYCLE | DONE | runtime identity boundary | registry runtime | signed enrollment approvals, identity generations, revocation, recovery approvals, provenance, and receipts |
| AUTHORITY-ACCEPTANCE-BOUNDARY | DONE | graph + capability model | registry pure Nix | reconcile-stage relationship/capability provenance, transitive issuer paths, issuer/parent binding, and non-amplification enforcement |
| SYSTEMD-VAULTD-INTEGRATION | DONE | secret boundary + research | registry; `packages/arbor-registry` | runtime gate/watcher plus real upstream systemd-vaultd socket integration |
| ENDPOINT-SERVICE-REGISTRY | DONE | network model + registry | worker | endpoints/services/runtime views and policy modules |
| NODE-SELECTION | DONE | registry source + graph | worker | selectors and copyable output |
| DEPLOY-PLANNER | DONE | deployment backend + selection | worker | plans/risk/acknowledgements |
| SECURITY-REVIEW | DONE | integrated implementation | reviewer | first review fixed MUST FIX findings |
| NIX-REVIEW | DONE | integrated implementation | reviewer | purity and store-boundary review; manager sanitization fixed |
| DISTRIBUTED-SYSTEMS-REVIEW | DONE | integrated registry | reviewer + fixer | schema/lineage/cycle/idempotency findings fixed |
| DEPLOYMENT-REVIEW | DONE | planner/backends | reviewer + fixer | ordering/cycle/backend/name findings fixed |
| FINAL-VALIDATION | DONE | reviews + fixes | lead + integration-test | all-systems component/root checks and pure scenarios passed |
| SOURCE-PRECEDENCE-MERGE | DONE | machine source + snapshot | worker; `packages/arbor-manager` | registry → local → session merge with provenance |
| VAULT-BINDING-VALIDATION | DONE | vault runtime boundary | worker; `packages/arbor-registry` | binding and public-identifier assertions |
| MULTI-NODE-RUNTIME-SCENARIO | DONE (test evidence) | runtime + recovery + manager | integration-test | root/parent/child/peer/standby scenario; live services not exercised |
| ARBOR-MANAGER-REMOTE | DONE | manager source integration | lead | standalone `pbert5/arbor-manager`, remote lock and local override |
| ARBOR-REGISTRY-REMOTE-SYNC | DONE | registry changes stabilized | lead | latest component published and root lock refreshed |
| DEPLOYMENT-REVIEW-FIX | DONE | deployment review | worker; manager | topology-safe canaries and snapshot-bound Colmena projection |
| RUNTIME-REVIEW-FIX | DONE | security/distributed review | worker; registry runtime | compatibility, lineage, malformed/conflict quarantine and locking |
| SECURITY-BOUNDARY-FIX | DONE (model boundary) | security review | worker; registry/manager | recovery/vault identifiers, recursive protections, redacted inspection |
| FINAL-GAP-AUDIT | DONE WITH FOLLOW-UPS | all integrated work | lead + reviewers | checks pass; long-lived bridge rotation failure recovery, production auth/topology, multi-host recovery, and real remote deployment remain external |
| ORBITDB-ADAPTER | DONE (optional daemon) | runtime Provider boundary | worker; `packages/arbor-registry/transport` | extracted OrbitDB/Helia daemon and executable two-daemon convergence test |
| EXPLICIT-PEER-EDGES | DONE | graph model | worker; `packages/arbor-registry/lib` | explicit peer records, cohorts, and selectors |
| ARBOR-CLI | DONE (offline + opt-in provider) | snapshot/selector/planner APIs | worker; `packages/arbor-manager` | inspect/list/export/plan and digest-bound direct provider execution |
| DEPLOYMENT-ACK-EXECUTION | DONE (opt-in adapter) | deployment planner + CLI | worker; `packages/arbor-manager` | immutable plan/risk/ack checks, direct/Colmena adapter protocol, batch receipts and resume; no real host contacted |
| VAULT-RUNTIME-TEST | DONE (mock + OpenBao HTTP + VM) | vault boundary | worker; `packages/arbor-registry` | initial readiness gate, restart-aware rotation, OpenBao delivery, real upstream socket credential test |
| VAULT-PROVIDER-VM | DONE | vault runtime boundary | worker; `packages/arbor-registry` | NixOS VM proves OpenBao HTTP → arbor-openbao-provider delivery |
| VAULT-PROVIDER-BRIDGE | DONE (initial path) | upstream vaultd boundary | worker; `packages/arbor-registry` | provider bridge groups credentials and proves OpenBao → provider → JSON contract → upstream vaultd socket; long-lived rotation VM remains follow-up |
| VAULTD-BRIDGE-SECURITY | DONE | provider bridge review | lead + independent reviewer | runtime-root, symlink, private-file, restart-retry, and malformed-command hardening |
| ACCEPTANCE-HARNESS | DONE (synthetic) | runtime + manager APIs | integration-test; repository tests | end-to-end pure scenario; live capabilities documented |
| HARDWARE-SNAPSHOT-SOURCE | DONE (validation) | machine-record model | worker; `packages/arbor-manager` | structured facts/content-addressed artifact references |
| TRANSPORT-CONVERGENCE-FIX | DONE (bounded) | optional OrbitDB daemon | worker; registry transport/runtime | peer bootstrap, replicated indexing, cursor forwarding, atomic index writes |
| SECURITY-HARDENING-ROUND-2 | DONE | final security review | workers; registry/manager | socket fail-closed, CLI redaction, recovery verifier/rotation safeguards |
| TRANSPORT-LOCK-OWNERSHIP-FIX | DONE | post-fix distributed/security review | worker; `packages/arbor-registry/transport` | ownership-safe stale takeover, heartbeat, and old-owner release tests |
| PROVIDER-EXECUTION-HARDENING | DONE | security review | lead; registry runtime + manager CLI | bounded/timed provider commands, contained backend stderr, full backend response identity |
| TRANSPORT-REPLAY-RECOVERY-HARDENING | DONE | distributed review | lead; registry transport | duplicate-event convergence, unreadable-record cursor retry, bounded quarantine, private state permissions |
| FINAL-POSTFIX-REVIEW | DONE | provider/transport hardening | independent security + Nix reviewers | cursor/authority/secret-key/vault-template MUST findings fixed and independently re-reviewed |
| SECURITY-DEPLOYMENT-FIX-ROUND-2 | DONE | final security/deployment review | lead; registry runtime + manager CLI | HTTPS boundary, redacted unsafe quarantine, strict endpoint/receipt validation, process-group timeout, stable transport cursors |
| REMOTE-MAIN-PROMOTION | DONE | standalone component sync | lead + worker | arbor-manager `66bcab5`, arbor-registry `ce54e00`; root lock refreshed and normal remote checks passed |
| UPSTREAM-VAULTD-VM | DONE (fixture) | upstream contract | integration-test; `packages/arbor-registry` | NixOS VM proves systemd-vaultd waits on the rendered JSON credential and delivers it through LoadCredential |
| TRANSPORT-RECOVERY-TESTS | DONE | transport/runtime recovery | worker; `packages/arbor-registry` | three-daemon reconnect/replay convergence and out-of-order identity-generation recovery with stale approver rejection |
| DEPLOYMENT-BOUNDARY-TESTS | DONE | deployment planning | worker; `packages/arbor-manager` | incompatible-target exclusion, Colmena canary/batch planning, failed receipts, resume validation, and backend identity |
| POSTFIX-SHOULD-FIXES | DONE | final review | lead + workers | precise transport evidence naming/topology assertions, explicit OpenBao readiness failure, and multi-batch deployment assertions |

The lead dispatches a newly unblocked row immediately; this table is not a
serial phase plan. Research agents may finish without changing repository
state; mutable workers own one branch/worktree and report commits.

## Active desktoptoodle/recovery queue

These rows define the current split between the recovery/credentials run and
the parallel non-secret host-parity run. They supersede any broader
`I4 DESKTOP-PARITY` assignment.

| ID | State | Dependencies | Owner / write set | Deliverable or gate |
|---|---|---|---|---|
| I4 SECRET-CONSUMER-HANDOFF | IN_PROGRESS | recovery/credential discovery | recovery/credentials run; `.env/`, `arbor-recovery-env`, secret catalog/materialization tooling, and generic path-based consumer interface | Make runtime secret paths available to host consumers without secret values entering Nix evaluation. BitLocker recovery material uses root-only paths under `/etc/nix-arbor/secrets/desktoptoodle/bitlocker/`; preserve stable credential identity in filenames or a manifest. |
| DESKTOPTOODLE-HOST-PARITY | IN_PROGRESS | none | parallel run on `agent/luna/desktoptoodle-host-parity`; `config/machines/desktoptoodle/` and other non-secret host configuration | Own monitor, Hyprland/Niri, GPU/NVIDIA, kernel, storage mounts, BitLocker unlock/mount service, Steam disk, audio/peripheral, workstation-service, hardware, and boot parity. It must consume secret paths only, never secret values. |
| A1 DESKTOP TEST ACTIVATION | BLOCKED | I4 SECRET-CONSUMER-HANDOFF + green `DESKTOPTOODLE-HOST-PARITY` | lead/integration | Before any `nixos-rebuild test` or `switch`, fetch `origin/agent/luna/desktoptoodle-host-parity`; if it exists and is reported green, inspect and semantically integrate it first. If absent or incomplete, do not perform final desktoptoodle activation; report activation blocked on that integration. |

The recovery/credentials run does not modify desktoptoodle monitor or host
parity configuration, GPU, kernel, storage, BitLocker service behavior, Steam,
audio/peripheral, workstation-service, or hardware/boot specialization. Those
remain owned by `DESKTOPTOODLE-HOST-PARITY`. Private credentials, password
hashes, SSH/service identities, BitLocker material, and other secret values
remain exclusively owned by the recovery/credentials run.
