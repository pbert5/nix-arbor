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
| SYSTEMD-VAULTD-INTEGRATION | DONE (boundary) | secret boundary + research | registry; `packages/arbor-registry` | runtime credential binding module; upstream vaultd/OpenBao remain injected |
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
| FINAL-GAP-AUDIT | DONE WITH FOLLOW-UPS | all integrated work | lead + reviewers | checks pass; live OrbitDB/OpenBao/systemd-vaultd/CLI execution remains explicitly incomplete |
| ORBITDB-ADAPTER | DONE (contract) | runtime Provider boundary | worker; `packages/arbor-registry/runtime` | legacy transport audit and bounded provider/adapter contract; live OrbitDB remains follow-up |
| EXPLICIT-PEER-EDGES | DONE | graph model | worker; `packages/arbor-registry/lib` | explicit peer records, cohorts, and selectors |
| ARBOR-CLI | IN_PROGRESS | snapshot/selector/planner APIs | worker; `packages/arbor-manager` | offline inspect/list/export/plan CLI |
| VAULT-RUNTIME-TEST | IN_PROGRESS | vault boundary | worker; `packages/arbor-registry` | mock readiness/rotation contract |
| ACCEPTANCE-HARNESS | IN_PROGRESS | runtime + manager APIs | integration-test; repository tests | end-to-end synthetic scenario evidence |

The lead dispatches a newly unblocked row immediately; this table is not a
serial phase plan. Research agents may finish without changing repository
state; mutable workers own one branch/worktree and report commits.
