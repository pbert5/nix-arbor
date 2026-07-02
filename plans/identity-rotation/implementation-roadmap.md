# Identity Rotation Implementation Roadmap

Status: in progress. Phase 1 registry primitives are partially implemented:
signed rotation intents and acknowledgements validate, and reconciliation
materializes derived `rotations.json` state. Exposure planning, operator CLI,
credential adapters, and deploy integration remain planned.

## Phase 1: Contract And Pure Reconciliation

Add the smallest registry primitives first:

- define rotation-intent and rotation-acknowledgement schemas;
- include rotation fields in canonical hashing and signing;
- validate authorization, exact target-event existence, fingerprints,
  deadlines, and modes;
- load rotation records without treating them as identity candidates;
- derive rotation progress from existing identity events, burns, delivery
  receipts, and new acknowledgements;
- materialize `rotations.json`;
- preserve last-good state when rotation records are invalid.

Likely code locations:

- `tools/clusterctl/clusterctl/canonical.py`
- `tools/clusterctl/clusterctl/registry.py`
- `tools/clusterctl/clusterctl/snapshot.py`
- `tools/clusterctl/clusterctl/follower.py`
- `tools/clusterctl/clusterctl/status.py`

Keep records on the existing per-leader event chain unless implementation
proves that doing so would break current chain semantics. Do not add a database
or dependency.

## Phase 2: Exposure Calculation

Implement a pure, inspectable planner that accepts explicit exposure and
returns affected identities with explanations.

Initial inputs:

- compromised or retired host names;
- removed users or guests;
- exact fingerprints;
- active registry identities;
- `privateDelivery.recipientHost`;
- signed delivery/activation receipts;
- host-age recipients and encrypted-ledger metadata;
- host users and `inventory/guest-access.nix`.

Initial output:

```json
{
  "targets": [],
  "externalRevocations": [],
  "publicIdentifiersIgnored": [],
  "unknownExposure": [],
  "evidence": []
}
```

Every included and ignored item must carry a human-readable reason. Unknown
service types require operator review rather than a guessed rotation.

Likely code locations:

- new focused `tools/clusterctl/clusterctl/rotation.py`
- `tools/clusterctl/clusterctl/main.py`
- inventory data only where existing data cannot express exposure

Do not put behavior in `inventory/`. Inventory remains data-first and
host entries remain behavior-light.

## Phase 3: Operator CLI

Planned commands:

```text
clusterctl identity rotate plan
clusterctl identity rotate start
clusterctl identity rotate status
clusterctl identity rotate advance
clusterctl identity rotate acknowledge
clusterctl identity rotate force-burn
```

### `plan`

- read inventory, policy, accepted registry, receipts, and current materialized
  state;
- calculate exposure closure;
- print the plan and ignored public identifiers;
- make no changes by default;
- support JSON output for review and tests.

### `start`

- require an explicit reviewed plan or repeatable selector arguments;
- append the signed rotation intent;
- in emergency mode, append burns or perform provider revocation first;
- in graceful mode, generate/publish replacement identities as staged;
- commit/publish only from the deploying leader.

### `status`

- show target-by-target progress;
- show pending required acknowledgements and deadline;
- show transport availability;
- print the next safe command.

### `advance`

- refuse unsafe transitions;
- activate replacements only after required local evidence;
- deprecate old generations after acknowledgement policy is satisfied;
- burn old fingerprints after the grace rule is satisfied;
- support `--dry-run`.

### `acknowledge`

- run on a follower after it has accepted the replacement root;
- sign exact replacement event hashes and accepted root CID;
- never choose the winning identity or authorize rotation itself.

### `force-burn`

- require a reason;
- display missed nodes and recovery consequences;
- append burns immediately;
- never rewrite or delete the original rotation intent.

All mutating commands should support the existing signing-key, no-commit, and
publication conventions where applicable.

## Phase 4: Credential Generators And Service Adapters

Reuse current native generators and provider CLIs. Add narrow adapters only
where rotation differs from initial generation.

Order:

1. SSH host identity
2. Yggdrasil
3. host age and re-encryption closure
4. IPNS publisher key
5. onion service identity
6. Radicle
7. Tailscale external revocation/re-enrollment guidance
8. git-annex credential/location handling

Each adapter declares:

- whether the registry identity is public, private, or external;
- how exposure is detected;
- how replacement is generated;
- how adoption is proven;
- how old authority is revoked;
- whether graceful overlap is safe.

Do not pretend an external revocation succeeded unless the provider command
returns verifiable success. Otherwise emit a pending operator action.

## Phase 5: Deploy And NixOS Integration

Leader deploy behavior:

- compare desired inventory and guest access with accepted registry exposure;
- warn when removed access leaves credentials requiring rotation;
- optionally run a non-mutating rotation plan during deploy preflight;
- append records only on the leader that is actively deploying;
- publish after successful append/reconcile.

Follower behavior:

- receive and validate rotation records;
- write signed acknowledgements only after accepting the replacement;
- never generate leader records while receiving or activating;
- retain last-good service state on invalid rotation metadata.

NixOS module behavior:

- expose paths and policy for the planner;
- materialize `rotations.json` under `/run/cluster-identity`;
- provide timers/services only for non-authoritative fetch, status, and
  acknowledgement duties;
- add evaluation or rebuild warnings where current configuration can prove a
  removed recipient;
- avoid activation-time registry mutation.

Likely Nix location:

- `dendrites/system/dendrites/cluster-identity/cluster-identity.nix`

No new dendrite or fruit is needed. Rotation is part of the existing
cluster-identity capability.

## Phase 6: Transport Handoff

Implement transport rotation only after ordinary identity rotation is stable.

- represent ordered transport steps in the rotation intent;
- require replacement policy authorization;
- publish through old and new routes during graceful overlap;
- consume signed node status/acknowledgements;
- enforce at least one trusted live route per step;
- apply deadlines and explicit exclusions;
- mark missed followers as requiring bootstrap;
- support immediate emergency revocation.

Start with leader IPNS plus onion fallback. Do not add Tailscale or additional
mirrors until the two-route invariant is tested.

## Phase 7: Documentation And Operator UX

Update durable docs after behavior exists:

- registry content contract;
- live registry architecture;
- transport contract;
- rollout playbook;
- troubleshooting;
- cluster-identity dendrite README;
- `clusterctl` cheat sheet;
- project roadmap.

Plans must not become the only documentation of implemented behavior.

## Suggested Commit Boundaries

1. `identity-registry: define rotation records and derived state`
2. `clusterctl: plan identity rotation from exposure`
3. `clusterctl: execute graceful and emergency rotation`
4. `cluster-identity: publish follower rotation acknowledgements`
5. `identity-registry: add staged transport handoff`
6. `docs: document identity rotation operations`

Each commit should pass focused tests independently.
