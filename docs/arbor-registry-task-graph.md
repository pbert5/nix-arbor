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
| REMOTE-MAIN-PROMOTION | DONE | standalone component sync | lead + worker | arbor-manager `66bcab5`, arbor-registry `16029ce`; root lock refreshed and normal remote checks passed |
| UPSTREAM-VAULTD-VM | DONE (fixture) | upstream contract | integration-test; `packages/arbor-registry` | NixOS VM proves systemd-vaultd waits on the rendered JSON credential and delivers it through LoadCredential |
| TRANSPORT-RECOVERY-TESTS | DONE | transport/runtime recovery | worker; `packages/arbor-registry` | three-daemon reconnect/replay convergence and out-of-order identity-generation recovery with stale approver rejection |
| DEPLOYMENT-BOUNDARY-TESTS | DONE | deployment planning | worker; `packages/arbor-manager` | incompatible-target exclusion, Colmena canary/batch planning, failed receipts, resume validation, and backend identity |
| POSTFIX-SHOULD-FIXES | DONE | final review | lead + workers | precise transport evidence naming/topology assertions, explicit OpenBao readiness failure, and multi-batch deployment assertions |
| VM-MULTINODE-ACCEPTANCE | VALIDATION | published registry/manager inputs | lead; `nix-arbor/tests/arbor-multinode-vm` | four isolated NixOS guests, real transport daemons, OpenBao/provider/vaultd secret flow, replay/quarantine, restart/reboot, virtual partition, runtime SSH, and graph-risk CLI evidence; passing smoke target, broader authority/deployment claims still open |
| VM-CROSS-PEER-CONVERGENCE | INTEGRATION | VM-MULTINODE-ACCEPTANCE | registry transport owner | raw cross-guest replication now passes with a shared realm; live relationship convergence remains a separate gate |
| VM-REMOTE-NIXOS-DEPLOYMENT | READY | VM-MULTINODE-ACCEPTANCE + manager direct backend | manager/integration owner | resolve a registry snapshot and perform real SSH/NixOS generation activation with receipt binding; current VM target proves SSH only |
| VM-LIVE-RELATIONSHIP-RECOVERY | READY | VM-CROSS-PEER-CONVERGENCE + runtime recovery APIs | registry/integration owner | accepted peer, active/standby parent, descendant, identity rotation, stale-generation rejection, and parent return in isolated guests |
| VM-REGISTRY-MODULE-STACK-OVERFLOW | DONE | vault runtime + NixOS module | registry owner | fixed and promoted as arbor-registry `823e02e`; normal published module path is exercised |

## Integrated VM acceptance queue

These rows are the active lead queue for the four-guest acceptance objective.
They intentionally distinguish transport reachability from replicated raw data,
accepted reconciliation, and materialized state.

| ID | State | Dependencies | Owner / write set | Deliverable |
|---|---|---|---|---|
| REGISTRY-NIXOS-MODULE-RECURSION | DONE | — | registry; arbor-registry | `823e02e` skips derivation metadata during public-value scans; focused package-valued module regression and component checks pass |
| ORBITDB-MANIFEST-ROOT-CAUSE | DONE | — | registry transport | `@orbitdb/core` 4.0.0 default IPFS ACL writes only the creator identity, so independent name opens produce different ACL blocks and manifest CIDs; focused regression added |
| ORBITDB-WRITER-SEMANTICS | DONE | ORBITDB-MANIFEST-ROOT-CAUSE | registry transport | realm-mode raw ACL is `write: ["*"]`; independent peers append in both directions while Arbor authorization remains above transport |
| TRANSPORT-REALM-DESIGN | DONE | ORBITDB-MANIFEST-ROOT-CAUSE | protocol/runtime | public per-registry realm ID plus protocol epoch deterministically scopes stream names and manifests; it is not a leader or authority |
| TRANSPORT-ACL-BOUNDARY | DONE | ORBITDB-WRITER-SEMANTICS | security/runtime | raw OrbitDB writes are permissive by design; signed record validation and accepted-state authorization remain the security boundary |
| TRANSPORT-BOOTSTRAP-CONTRACT | DONE | TRANSPORT-REALM-DESIGN; TRANSPORT-ACL-BOUNDARY | registry transport | `ARBOR_REGISTRY_REALM_ID`/epoch derive a common address; bootstrap metadata persists and conflicts fail closed; status exposes non-secret diagnostics |
| DETERMINISTIC-INDEPENDENT-OPEN | DONE | TRANSPORT-BOOTSTRAP-CONTRACT | registry transport | separate state directories and identities independently open one realm address; restart preserves it |
| ORBITDB-CROSS-GUEST-CONVERGENCE | INTEGRATION | DETERMINISTIC-INDEPENDENT-OPEN | registry transport + VM | bounded four-VM raw replication and multi-writer assertion passes; live relationship convergence remains separate |
| CROSS-GUEST-VM-CONVERGENCE | INTEGRATION | DETERMINISTIC-INDEPENDENT-OPEN | VM integration | VM status proves one realm/address, then root-a→child and child→root-b raw events replicate within bounded waits |
| ACCEPTED-STATE-CROSS-GUEST | DONE | CROSS-GUEST-VM-CONVERGENCE | registry reconciliation | bounded VM assertion proves a signed root-a record reaches child raw state, accepted history, and materialized projection |
| LIVE-RELATIONSHIP-ACCEPTANCE | READY | ACCEPTED-STATE-CROSS-GUEST | registry reconciliation | live signed peer, active/standby parent, and grandchild edges |
| SERVICE-ENDPOINT-CROSS-GUEST | READY | ACCEPTED-STATE-CROSS-GUEST | registry runtime | live service and provider-neutral endpoint advertisement/resolution |
| VM-SERVICE-ENDPOINT-INTEGRATION | BLOCKED | ORBITDB-CROSS-GUEST-CONVERGENCE | registry runtime | live service and provider-neutral endpoint advertisement/resolution in the VM network |
| IDENTITY-RECOVERY-VM | BLOCKED | LIVE-RELATIONSHIP-ACCEPTANCE | registry runtime | runtime identity replacement, recovery authorization, stale-generation rejection, and grandchild survival |
| REMOTE-NIXOS-ACTIVATION | BLOCKED | LIVE-RELATIONSHIP-ACCEPTANCE; published module path | manager/integration | registry-derived immutable plan and real SSH/NixOS activation with receipt |
| REMOTE-NIXOS-ACTIVATION-FAILURE | BLOCKED | REMOTE-NIXOS-ACTIVATION | manager/integration | failure receipt, identity-bound retry/resume, and no false success |
| COLMENA-VM | BLOCKED | REMOTE-NIXOS-ACTIVATION | deployment | serious real multi-guest Colmena attempt, or explicit VM-environment blocker |
| FAILED-VAULT-CONSUMER-ROTATION | DONE | — | vault/runtime | VM masks the consumer during rotation, observes provider restart failure without advancing consumer state, then restores and verifies retry at the latest generation |
| HARNESS-NORMAL-MODULE-PATH | DONE | REGISTRY-NIXOS-MODULE-RECURSION | VM integration | acceptance uses the published `vault-runtime-upstream` module export |
| SECRET-LEAK-REGRESSION | DONE (existing smoke) | — | security test | runtime sentinel absence from closure, public state, logs, and receipts; broaden when deployment exists |
| ACCEPTANCE-REVIEW | REVIEW | integrated VM implementation | independent reviewer | adversarial harness review; not yet performed |
| DISTRIBUTED-SYSTEMS-REVIEW | REVIEW | integrated VM implementation | independent reviewer | convergence, partition, replay, and recovery review; not yet performed |
| SECURITY-REVIEW-VM | REVIEW | integrated VM implementation | independent reviewer | identity, authority, credentials, and secret-boundary review; not yet performed |
| NIX-DEPLOYMENT-REVIEW | REVIEW | integrated VM implementation | independent reviewer | module, store, snapshots, SSH, activation, and Colmena review; not yet performed |

The lead dispatches a newly unblocked row immediately; this table is not a
serial phase plan. Research agents may finish without changing repository
state; mutable workers own one branch/worktree and report commits.
