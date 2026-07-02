# Identity Rotation Plan

Status: planned. The operator rotation workflow is not implemented yet; the
registry can now validate signed rotation intents and acknowledgements and
materialize derived `rotations.json` state.

The existing registry already supports signed identity events, staged and
active identities, deprecation, irreversible burns, delivery receipts,
append-only supersedence, follower checkpoints, IPFS/IPNS publication, onion
fallbacks, and signed node status. This plan composes those mechanisms into a
safe rotation workflow without weakening the meaning of `burned`.

## Settled Decisions

- `burned` continues to mean immediately ineligible and permanently
  non-reusable. There is no transitional `burning` identity state.
- A signed append-only rotation intent records that replacement work is
  required. It does not itself revoke an identity.
- Graceful rotation and emergency compromise response are separate modes.
- Emergency rotation burns or externally revokes compromised credentials
  immediately. Availability recovery follows the security action.
- Graceful rotation installs and verifies replacements before deprecating and
  burning old material.
- Rotation operates on secrets and capabilities, not every identifier that was
  merely visible to an exposed user or host.
- Registry transport identities rotate one route at a time. At least one
  trusted route remains usable during a graceful handoff.
- Unreachable followers do not block rotation forever. Completion uses an
  explicit acknowledgement policy, deadline, and operator-visible exceptions.
- Only the leader performing a deploy may append rotation records or publish
  replacement registry entries. Receiving or activating a configuration never
  mutates a leader's registry.
- All rotation records, acknowledgements, replacement identity events,
  deprecations, and burns are append-only.

## Planned Documents

- [security-model.md](security-model.md) defines rotation triggers, exposure
  closure, and service-specific consequences.
- [registry-contract.md](registry-contract.md) defines the planned signed
  records, derived state, and safety invariants.
- [implementation-roadmap.md](implementation-roadmap.md) maps the work onto
  `clusterctl`, inventory, the NixOS module, and documentation.
- [testing-and-rollout.md](testing-and-rollout.md) defines unit, MicroVM, and
  operator acceptance tests.

## Intended Operator Outcome

The eventual operator flow should be:

```text
detect exposure or planned retirement
  -> calculate affected credentials
  -> append a rotation intent
  -> replace credentials
  -> verify adoption when graceful
  -> deprecate old identities
  -> burn old fingerprints
  -> report exceptions and completion
```

For a confirmed or suspected compromise:

```text
detect compromise
  -> revoke external access and append burns immediately
  -> generate and deploy replacements
  -> restore transport and service availability
```

## Non-Goals

- Rotating every public address merely because it was observable.
- Treating git-annex UUIDs, Tailscale IPs, or other public identifiers as
  secrets.
- Waiting forever for every historically enrolled or currently unreachable
  follower.
- Allowing an activation script or registry receiver to generate credentials
  or append authoritative events.
- Building a general-purpose graph database. The first implementation should
  derive exposure from existing inventory and receipt data, with small explicit
  metadata additions only where evidence is otherwise unavailable.
