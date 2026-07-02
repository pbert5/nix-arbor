# Identity Rotation Testing And Rollout

Status: planned.

## Unit Tests

### Record validation

- accept a correctly signed graceful intent targeting an existing event;
- accept a correctly signed emergency intent;
- reject unknown, future, or guessed event hashes;
- reject mismatched subject, generation, fingerprint, or embedded event;
- reject unauthorized leaders;
- reject malformed deadlines and impossible acknowledgement thresholds;
- reject a graceful transport plan that removes every trusted route;
- preserve last-good state on invalid records.

### Exposure calculation

- compromised host includes private identities installed or delivered there;
- removed guest includes hosts granted through guest-access inventory;
- compromised age recipient includes secrets encrypted to that recipient;
- shared credential exposure expands to every consumer of that credential;
- visible public Yggdrasil addresses do not rotate unrelated nodes;
- Tailscale IPs and git-annex UUIDs are reported as ignored public identifiers;
- reusable provider tokens are included;
- unknown service exposure is reported for operator review.

### Derived progress

- intent alone is `replacement-pending`;
- staged replacement remains pending;
- active replacement without acknowledgements is
  `awaiting-acknowledgements`;
- sufficient valid acknowledgements become `ready-to-retire`;
- deprecation produces `deprecated`;
- exact old fingerprint burn produces `complete`;
- emergency burn without replacement produces `emergency-incomplete`;
- invalid or stale acknowledgements do not count;
- excluded and unreachable followers remain visible.

### Safety

- a burn immediately removes the fingerprint regardless of rotation state;
- cancellation cannot resurrect a burned fingerprint;
- acknowledgement cannot select a conflict winner;
- lower-generation rollback remains rejected;
- supersedence and rotation records do not interfere;
- receiver or activation paths never append leader records.

## CLI Tests

- `rotate plan` is read-only and deterministic;
- JSON plan output round-trips into `rotate start`;
- `rotate start --dry-run` changes no files;
- graceful start appends intent and replacement but not burn;
- emergency start appends burn before attempting replacement;
- `rotate advance` refuses missing acknowledgements;
- deadline/exclusion policy permits a bounded advance;
- `force-burn` records reason and recovery consequences;
- Git commit and IPFS publication flags match existing CLI conventions.

## MicroVM Scenarios

Extend `experiments/cluster-identity-microvm`.

### Graceful service rotation

1. Leader publishes generation 1.
2. Follower accepts generation 1.
3. Leader appends graceful rotation intent.
4. Leader publishes generation 2 staged/active.
5. Follower accepts generation 2 and writes a signed acknowledgement.
6. Leader collects acknowledgement and deprecates generation 1.
7. Leader burns generation 1.
8. Follower keeps generation 2 active.
9. Both original and replacement events remain immutable in the registry.

### Emergency compromise

1. Follower uses generation 1.
2. Leader appends emergency intent and burn.
3. Follower immediately rejects generation 1.
4. Replacement generation 2 is published afterward.
5. Follower recovers on generation 2.
6. No acknowledgement delays the initial burn.

### Access removal

1. Guest access grants a guest a follower host.
2. A delivered private service is recorded for that host.
3. Desired inventory removes the guest.
4. Planner includes the delivered secret and host identities.
5. Planner excludes unrelated public identities on other hosts.

### Transport handoff

1. Follower trusts IPNS primary plus onion fallback.
2. Leader introduces a new primary through both routes.
3. Follower accepts and acknowledges the new primary.
4. Old primary is retired while onion remains available.
5. Onion is then replaced while new IPNS remains available.
6. A follower missing the deadline is marked for re-enrollment.
7. At no graceful step are both trusted routes unavailable.

### Compromised transport

1. Mark old primary compromised.
2. Burn/revoke it without waiting for followers.
3. Recover through unaffected fallback and policy-authorized replacement.
4. Verify old-key signatures cannot authorize the replacement alone.

## Repository Checks

Run the narrowest relevant checks after each phase:

```text
clusterctl unit tests
identity registry Nix check
cluster identity MicroVM suite
Nix parsing for changed modules and experiment files
git diff --check
```

Do not run a deployment or activation command without explicit permission.

## Rollout Order

1. Land schemas, validation, and read-only status.
2. Land read-only exposure planning.
3. Exercise plans against current inventory without mutation.
4. Enable graceful rotation for one ordinary service.
5. Enable emergency burn-first mode.
6. Add follower acknowledgements.
7. Add host-age closure and re-encryption.
8. Add IPNS/onion transport handoff.
9. Enable deploy preflight warnings.
10. Consider automation only after repeated successful manual rotations.

## Acceptance Criteria

The feature is ready when:

- an operator can explain why every credential is or is not in a rotation;
- emergency compromise never waits on availability acknowledgements;
- graceful transport rotation never intentionally removes the final trusted
  route;
- followers cannot mutate leader registries;
- old events remain immutable and burned fingerprints cannot return;
- unreachable followers have an explicit recovery state;
- VM tests demonstrate graceful, emergency, access-removal, and transport
  handoff paths.
