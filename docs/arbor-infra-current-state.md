# Arbor infrastructure current state

Planning snapshot: 2026-09-18.

This document records the current implementation and bring-up state for the
Arbor infrastructure carried into the WS1 reconciliation branch. GitHub
tracking issue [#9](https://github.com/pbert5/nix-arbor/issues/9) is the durable
execution contract. Workstream issues [#10](https://github.com/pbert5/nix-arbor/issues/10)
through [#16](https://github.com/pbert5/nix-arbor/issues/16) own the remaining
work.

## Executive summary

Arbor Manager and Arbor Registry are no longer missing architectural foundations. Their core models, runtime boundaries, safety invariants, planning surfaces, and substantial VM/component validation already exist.

The remaining work is primarily production integration:

1. finish runtime secret consumer delivery and production OpenBao auth
2. bootstrap two real Registry participants on the private network
3. establish accepted live relationships and service/endpoint discovery
4. execute one harmless real remote deployment through Arbor Manager
5. prove live identity-generation recovery
6. complete final integration, independent review, GitHub relationship audit,
   and authorized promotion

A cluster should not be described as operational until the live acceptance conditions in issue #9 are satisfied.

## Repository provenance

### Nix Arbor

WS1 reconciliation provenance:

- `main`: `9c5f2b4f37db7b9d336e70db498e3d272eba1314`
- `arbor-infra-dev`: `3f1349c138cb0cc91abfc419112cd35965be12ef`
- merge base: `ae1f29cc82f3ea6fe93f02769930e6c5cd08c6c3`
- reconciled WS1 merge checkpoint: `9239a61cd34db8538eb06f1ab898b5d883236f86`
- final reviewed branch: `agent/workstream-owner/ws1-arbor-main-reconcile`
- draft PR: #18

The WS1 branch is the reviewed integration candidate and retains two-parent
ancestry. It does not authorize a default-branch merge or live activation.

### Arbor Manager

Canonical development line:

```text
pbert5/arbor-manager
branch: arbor-infra-dev
tip: 390ccc7bf56418b0badab22cd4227794726a5bd9
```

### Arbor Registry

Canonical development line:

```text
pbert5/arbor-registry
branch: arbor-infra-dev
tip: 7a07be55ea31898aceb77da229bb119a1ca26c29
```

The Nix Arbor development branch composes/pins these standalone component repositories.

## Implemented state

### Arbor Registry

Implemented and validated at component/VM level:

- canonical signed record envelopes
- retained raw history and deterministic reconciliation
- accepted, quarantined, and materialized state separation
- node identities and identity generations
- local genesis for independently self-rooted nodes
- enrollment, revocation, and recovery lifecycle
- relationship graph semantics
- parent, standby-parent, peer, and recovery edges
- multiple-parent support
- parent-cycle diagnostics
- capability-scoped authority
- non-amplification enforcement
- separate authority provenance
- compatibility epoch/feature handling
- bounded quarantine
- endpoint and service records
- durable local runtime/provider path
- optional OrbitDB/Helia transport adapter
- realm/bootstrap persistence
- transport replay/idempotence/reconnect hardening
- OpenBao runtime provider
- systemd-vaultd provider bridge
- NixOS policy/runtime modules
- recovery signature-verifier boundary
- VM/runtime acceptance for major individual pieces

The security pipeline remains:

```text
raw transport
  -> framing/schema/signature/authority validation
  -> accepted history
  -> materialized state
  -> consumers
```

Raw network/transport data is not authority.

### Arbor Manager

Implemented:

- `lib.mkMachines`
- local and immutable Registry snapshot sources
- source precedence and per-field provenance
- data-only Registry hardware snapshot/artifact contract
- deterministic redacted machine/deployment snapshots
- graph selectors
- graph-ordered deployment planning
- compatibility/reachability exclusions
- canaries and deterministic batches
- acknowledgement digest
- optional Colmena projection
- offline CLI
- offline TUI
- immutable snapshot verification
- explicit backend-executable execution boundary
- per-node structured backend requests/results
- backend timeout/error containment
- resumable authenticated receipts

Arbor Manager is intentionally not the Registry and does not query live transport during Nix evaluation.

### Root Nix Arbor integration

Reusable root profiles already exist for:

- Arbor operator tooling
- Arbor Registry participation
- private-Ygg / Arbor Network Manager participation
- normal server/desktop composition

The obvious first real hosts have intentionally not yet been fully opted into the live Arbor participant profiles. That activation is gated on the work below.

## Implemented but not yet exercised as the production path

The following should be treated as implemented or substantially implemented, but not yet accepted as production behavior:

- persistent two-host Registry bootstrap
- real private-Ygg Registry convergence on the intended hosts
- accepted relationship creation on physical/persistent machines
- cross-node service/endpoint discovery
- production OpenBao authentication
- long-lived credential rotation with restart failure/recovery
- real remote NixOS deployment through Arbor Manager
- multi-host identity-generation loss/recovery
- final participant-profile activation and branch promotion

Synthetic, unit, integration, and VM evidence should remain clearly distinguished from live-host evidence.

## Remaining work

### WS1 - branch reconciliation

Issue: [#10](https://github.com/pbert5/nix-arbor/issues/10)

Reconcile the 8 unique development commits with the 33 newer `main` commits. Preserve both current mainline work and Arbor infrastructure intent. Re-run root validation on the reconciled base.

### WS2 - secret consumer and production OpenBao

Issue: [#11](https://github.com/pbert5/nix-arbor/issues/11)

Finish the runtime-only consumer interface, production auth injection, real consumer delivery, changed-value refresh/restart, last-good retention, and recovery after refresh failure.

### WS3 - live Registry/private network bootstrap

Issue: [#12](https://github.com/pbert5/nix-arbor/issues/12)

Bring up two independently self-rooted real nodes, establish private network transport, persist realm/bootstrap state, prove convergence, reconnect, replay, and restart behavior.

### WS4 - live relationships and service discovery

Issue: [#13](https://github.com/pbert5/nix-arbor/issues/13)

Create accepted bounded relationship authority between the live nodes, verify consistent materialized state, publish one service/endpoint, and resolve it cross-node.

### WS5 - real Manager deployment

Issue: [#14](https://github.com/pbert5/nix-arbor/issues/14)

Implement/prove the direct NixOS deployment adapter first. Exercise digest/acknowledgement binding, one harmless real activation, failure handling, receipts, and resume. Treat real Colmena support as a follow-on after the direct path is green.

### WS6 - live recovery drill

Issue: [#15](https://github.com/pbert5/nix-arbor/issues/15)

Prove controlled generation loss/retirement, a new generation, recovery authorization, stale-generation rejection, and restoration of the intended accepted topology.

This issue contains an explicit destructive-operation human boundary.

### WS7 - final integration and review

Issue: [#16](https://github.com/pbert5/nix-arbor/issues/16)

Integrate reviewed heads, run fresh root/component/live acceptance, independent security/Nix/distributed/deployment review, and the mandatory GitHub relationship-realization audit.

## Dependency shape

```text
WS1 reconciles/freeze integration base
  |
  +--> WS2 secret/OpenBao ---------\
  +--> WS3 Registry/network --------+--> WS4 relationships/services --> WS6 recovery
  +--> WS5 deployment backend -----/                 |                    |
                                                    +--------------------+--> WS7
WS1 ---------------------------------------------------------------> WS7
WS2 ---------------------------------------------------------------> WS7
WS5 ---------------------------------------------------------------> WS7
```

WS2, WS3, and WS5 are contract-parallel after WS1 freezes the integration base, subject to per-host shared-resource locks.

## Minimum live acceptance

The tracking goal is not complete until there is fresh evidence for all blocking items:

1. reconciled root branch passes required checks
2. Manager component checks pass
3. Registry component checks pass
4. node A has persistent self-rooted identity and accepted state
5. node B has persistent self-rooted identity and accepted state
6. real Registry transport converges and reconverges
7. an accepted relationship is consistent on both nodes
8. a service/endpoint is resolved cross-node
9. an OpenBao-backed real consumer receives runtime-only credential material
10. credential refresh/restart failure preserves last-good data and later recovers
11. Manager performs one harmless real remote activation from an immutable acknowledged plan
12. deployment receipt/resume is exercised
13. controlled recovery rejects the stale generation and restores intended topology
14. independent review has no unresolved blocking finding
15. GitHub relationship/provenance audit is complete

## Safety and architecture invariants

Do not relax these to make bring-up easier:

- private keys, secrets, recovery material, tokens, and live membership remain outside Git/Nix evaluation
- transport reachability does not create authority
- OpenBao is privileged material storage/authorization, not Registry truth
- Registry owns signed records, acceptance, reconciliation, and materialized state
- Manager consumes immutable accepted snapshots and trusted local composition
- Registry data cannot inject arbitrary executable Nix
- capability delegation cannot amplify authority
- nodes remain independently self-rooted
- deployment remains explicit, inspectable, digest-bound, and acknowledged
- destructive host/identity operations require the owning issue's explicit authorization boundary

## Operator interpretation

The project is past its core architecture phase.

The next milestone is not another abstraction layer. It is a vertical live circuit:

```text
first node local genesis
  -> second node local genesis
  -> private Registry convergence
  -> accepted relationship
  -> accepted service record
  -> OpenBao runtime delivery
  -> immutable Manager plan
  -> harmless remote activation
  -> receipt
  -> controlled recovery
```

When that circuit and the final reviews are green, Arbor Manager + Arbor Registry can reasonably be treated as operational infrastructure rather than development-only components.

## GitHub execution ledger

Use tracking issue [#9](https://github.com/pbert5/nix-arbor/issues/9) as the overall execution contract.

Workstream issues:

- [#10](https://github.com/pbert5/nix-arbor/issues/10) WS1 reconciliation
- [#11](https://github.com/pbert5/nix-arbor/issues/11) WS2 OpenBao/consumer
- [#12](https://github.com/pbert5/nix-arbor/issues/12) WS3 live Registry/network
- [#13](https://github.com/pbert5/nix-arbor/issues/13) WS4 relationships/services
- [#14](https://github.com/pbert5/nix-arbor/issues/14) WS5 deployment backend
- [#15](https://github.com/pbert5/nix-arbor/issues/15) WS6 recovery
- [#16](https://github.com/pbert5/nix-arbor/issues/16) WS7 integration/review/audit

The connected GitHub surface used to create these issues does not expose every first-class parent/dependency relationship mutation. A Codex relationship-auditor/reconciliation run should realize those native relationships where GitHub supports them before final integration.
