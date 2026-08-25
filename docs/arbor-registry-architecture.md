# Arbor Registry architecture

This document freezes the initial extraction boundary for `arbor-registry` and
its integration with `arbor-manager`. It is deliberately a small, inspectable
foundation; live transport and privileged credential delivery remain runtime
concerns.

## Ownership

* Nix/Git defines reusable construction: profiles, module selectors, policy,
  secret requirements/bindings, static overrides, and bootstrap policy. It
  never contains mutable node identities, private keys, credentials, or live
  membership.
* Arbor Registry distributes signed typed records over an interchangeable
  transport (OrbitDB/Helia is an adapter), validates them, reconciles accepted
  history, and serves accepted/materialized state.
* OpenBao authorizes privileged assertions and stores private/runtime material.
  It is not the registry database.
* Arbor Manager resolves accepted registry snapshots and local sources into
  reproducible machine records, plans operations, and invokes deployment
  backends.

The pipeline is always:

```text
raw transport -> envelope/schema/signature/authority validation
              -> accepted history -> materialized state -> consumers
```

Raw transport data, even when signed by a cryptographically valid key, never
grants authority by itself.

## Record envelope and families

Every record has a canonical signed envelope containing:

```text
protocolEpoch, wireVersion, schema, schemaVersion, recordVersion,
recordId, generation, issuer, subject, predecessor, createdAt, expiresAt,
requiredFeatures, optionalFeatures, payload, signature
```

Initial record families are `node-identity`, `identity-generation`,
`relationship`, `capability`, `machine-facts`, `hardware-snapshot`,
`configuration-intent`, `endpoint`, `service`, `compatibility`,
`recovery-authorization`, `revocation`, and `receipt`. They are explicit
schemas, not one generic mutable JSON document.

The first implementation may use a deterministic in-process transport for
tests and snapshots. OrbitDB integration is a provider behind the same
append/fetch interface and must not be required by Nix evaluation.

The steady-state input is `github:pbert5/arbor-registry`. During local
component development Nix Arbor uses `--override-input arbor-registry
path:./packages/arbor-registry`; the checked-out component remains available
for the repository's local workflow.

## Graph semantics

Relationships are immutable signed assertions plus state-transition records.
They contain `relationshipId`, `from`, `to`, `kind`, `scope`, `autonomy`,
`status`, `priority`, `issuer`, `authorityRoot`, `generation`, and provenance.

`parent`/`follower` is directed; `standby-parent` is directed but excluded from
active traversal until promoted; `peer` is reciprocal and canonicalized; a
`recovery` edge records reattachment and does not itself create lineage.
Multiple parents are valid and retain separate authority paths. Siblings are
derived from common active parents. `active`, `suspended`, and `severed` are
distinct; severing preserves history and descendants. Autonomy is scoped and
uses the clear values `dependent` and `independent`.

Parent cycles are errors with deterministic strongly-connected-component
diagnostics. Peer SCCs are informational cohorts, not parent cycles. Derived
labels such as root/parent/follower are queries, never node roles.

Authority propagation is capability-scoped and monotonic: a child cannot
delegate more than it received, and grants from separate authority roots are
never merged. Observation, authority, and secret/credential access are
separate projections.

## Compatibility and quarantine

Compatibility is feature/schema based, not a Git or package-version equality.
Epoch is a security boundary. Unknown epoch/schema/record kind/version or
unsupported required features are retained in bounded quarantine and cannot
change accepted state. Optional unsupported records may make a relationship
`degraded`; required unsupported records make it `incompatible` while the
last-good projection remains active. Existing relationships are retained
across version drift; breaking changes require an explicit signed migration.

Acceptance order is framing limits, canonical parse, tuple support, hash,
signature, issuer authority, predecessor/relationship binding, generation and
anti-rollback, conflict/supersedence, then atomic materialization.

## Machine source contract

`arbor-manager.lib.mkMachines` accepts a pure `source` of normalized entries;
`machinesPath` remains a compatibility shorthand for the static directory
source. A source returns entries of the form:

```nix
{
  record = {
    identity = { id = "node"; aliases = [ ]; };
    platform = "x86_64-linux";
    hardware = { snapshot = null; modules = [ ]; };
    intent = { profiles = [ ]; modules = [ ]; features = [ ]; };
    relationships = [ ];
    endpoints = [ ];
    services = [ ];
    compatibility = { protocolEpoch = 1; }; 
    metadata = { }; 
    provenance = { source = "registry"; digest = "..."; };
  };
  modules = [ ];
}
```

Registry snapshots are immutable JSON/Nix data supplied before evaluation.
Nix never contacts OrbitDB. The resolved machine record preserves per-field
source and override provenance. Precedence is registry snapshot, then
committed local machine definition, then explicit CLI/session override; Nix
module priority rules still apply within a source's module list.

Arbitrary executable Nix from the registry is forbidden. Arbor Manager
validates registry hardware as either structured snapshot metadata (`format`,
positive `version`, and an attribute-set `facts` payload) or an immutable
artifact reference with a `sha256:<64 lowercase hex>` content address. The
forms are mutually exclusive, artifact references are not fetched or
evaluated, and `hardware.modules` is rejected. Executable
`hardware-configuration.nix` and `configuration.nix` modules remain explicit
members of local sources.

## Runtime identity and secrets

The flake can declare `cluster.registry` identity requirements and
`cluster.vault` secret requirements/bindings, but private signing, age,
libp2p, SSH, OpenBao, and service material are runtime-only. Rebuild/recovery
gets a new identity generation when required, revokes the old generation, and
reattaches relationships only through signed recovery authorization.

Registry service/endpoint records expose names, protocols, addresses,
reachability metadata, and policy references. They never expose secret
values. OpenBao Agent plus systemd-vaultd provides credentials through native
systemd credentials; rotation uses restart or an explicitly refresh-safe
mechanism because `LoadCredential` is immutable for a running process.

## Manager/deployment boundary

Manager offers graph selectors `local`, `children`, `descendants`, `parents`,
`ancestors`, `peers`, and `accessible`, with `all` reserved for an explicitly
defined union rather than an implicit everything operation. It emits an
inspectable resolved snapshot and deployment plan before acting.

Direct deployment is the small-scope backend. Colmena is an optional backend
fed from the same resolved records; it is never inventory or authority.
Because Colmena has no graph ordering transaction, Arbor plans graph-critical
targets, canaries/batches, reachability loss, compatibility failures, and
acknowledgement before invoking it.

## Security invariants

The initial implementation tests these invariants: raw transport is not
authority; no privilege amplification; separate authority provenance; unknown
records cannot poison accepted state; no private material or secret values in
Git/store; service metadata does not grant credentials; unauthorized
signatures remain unauthorized; suspension/severing preserve history; network
reachability is not authorization; revoked identity generations do not
resurrect; and local overrides do not silently alter security authority.

The current extracted milestone also includes an optional runtime package
with Ed25519 key storage, durable local ingestion, compatibility/lineage
quarantine, and recovery metadata. Those runtime facilities are deliberately
transport-provider and secret-provider neutral. It still does not claim a
production OrbitDB/Helia adapter, live OpenBao or systemd-vaultd deployment,
or live SSH/Colmena execution; those require separate executable integration
tests and must not be inferred from the pure library or local runtime fixture.

## Migration classification

Preserve signed canonical events, validation, reconciliation, accepted and
materialized state, enrollment, receipts, recovery, and the transport daemon's
bounded/idempotent behavior. Adapt the Nix handoff, transport API, secret
provider interface, and manager source boundary. Replace fixed leader/follower
roles with graph relationships and replace committed private identity state
with runtime generations. Drop Git/SSH/Radicle as steady-state registry
transport, IPFS Cluster coordination, and unreviewed Bao auto-unseal from the
initial extraction.
