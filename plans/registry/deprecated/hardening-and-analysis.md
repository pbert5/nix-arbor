# Hardening And Analysis

## Acceptance Criteria

The registry MVP is complete when:

```text
1. nix flake check passes.
2. r640-0, desktoptoodle, and t320-0 build with the cluster-identity dendrite.
3. /etc/cluster-identity/policy.json exists on enrolled hosts.
4. /var/lib/cluster-identity/age/host.agekey exists on enrolled hosts.
5. sops-nix can decrypt host-targeted secrets on enrolled hosts.
6. cluster-identity-fetch.timer exists and runs.
7. clusterctl registry init/validate/reconcile/materialize work.
8. A leader can publish flake identity records into registry events.
9. Registry events include privateDelivery metadata when flake records include private blocks.
10. A follower can fetch and materialize /run/cluster-identity.
11. clusterctl deploy HOST --dry-run resolves active live target and fallback host-bootstrap target.
12. Leaders run best-effort `clusterctl identity publish` during activation.
13. Operator docs and dendrite docs exist.
14. README.md links to the live registry workflow.
```

## Implemented Pieces

Implemented in the current worktree:

- `sops-nix` flake input.
- `inputs.sops-nix.nixosModules.sops` imported into host assembly.
- flake-pinned `sops` app and package output.
- `system/cluster-identity` SOPS key file config.
- `/var/lib/cluster-identity/age` tmpfiles directory.
- encrypted private service identity SOPS ledger placeholder.
- encrypted host age private key recovery SOPS ledger placeholder.
- `.sops.yaml` creation rules encrypted to current leaders.
- identity inventory metadata for both SOPS ledgers.
- identity policy check requiring SOPS ledger paths.
- `clusterctl identity publish` reading the flake identity ledger.
- `clusterctl identity publish` mirroring private blocks into registry
  `privateDelivery` metadata.
- duplicate detection including `privateDelivery`.
- timestamp-aware registry reconciliation.
- active host age private keys verified on `r640-0`, `desktoptoodle`, and
  `t320-0`; derived public recipients match inventory.
- SSH bundle delivery smoke verified on `r640-0`, `desktoptoodle`, and
  `t320-0` with root-owned `0400` target files.
- leader activation hook for best-effort `clusterctl identity publish`.
- `dev-machine` and `compute-worker` moved out of active inventory into
  `inventory/deprecated/`.

## Planned Work

High-priority next pieces:

- implement real SSH signature verification
- generate signed encrypted private bundle manifests from SOPS ledger entries
- add `clusterctl host-age bootstrap HOST`
- add service identity generation commands
- add service identity rotation commands
- add host age key rotation commands
- add follower decryptability-aware selection
- add richer registry schema validation

Later pieces:

- generate declarative Git remotes from inventory policy
- allow node-signed receipts through a restricted push path
- add repair-mode deploy candidate selection
- reload or restart service consumers when materialized state changes
- expose `/run/cluster-identity/registry-newest.json` separately from locally
  usable `active.json`
- add tests for burned fingerprint reintroduction
- add tests for timestamp ordering across duplicate generations
- add tests for private-delivery receipt gating

## Open Design Questions

### SOPS Ledger Shape

The encrypted ledger files exist and are encrypted to leader recipients. From
the visible YAML shape, their payload maps are still placeholders:

```text
inventory/keys/identities/cluster-private-identities.sops.yaml: identities = {}
inventory/keys/followers/host-age-private-keys.sops.yaml: hosts = {}
```

This local user could not decrypt them because no leader age identity was
available in standard SOPS locations. The planned payload shape should be
regular enough for `clusterctl` to generate and update paths without
stringly-typed surprises.

Candidate private service shape:

```yaml
schema: cluster.identity.private.v1
identities:
  yggdrasil:
    r640-0:
      generation: 2
      keyGeneratedAt: "2026-05-11T05:00:00Z"
      privateKey: REPLACE_ME
```

Candidate host age recovery shape:

```yaml
schema: cluster.identity.host-age-private.v1
hosts:
  r640-0:
    generation: 1
    keyGeneratedAt: "2026-05-11T04:12:55Z"
    publicKey: age1...
    privateKey: AGE-SECRET-KEY-...
```

### Registry Bundle Storage

Decision:

- small host-targeted encrypted bundles can live in `bundles/`
- large or frequently rotated material should use a content-addressed external
  store later
- every bundle gets a signed manifest with recipient fingerprints, ciphertext
  hash, plaintext hash, expected public identity, and leader signature

### Rebuild-Time Publishing

Decision: leaders should automatically run `clusterctl identity publish` during
activation.

Reasoning:

- registry freshness should be easy and regular
- flake identity truth should be mirrored whenever a leader rebuilds
- explicit publish remains available for manual repair or narrow updates
- activation publishing is best-effort so a transient registry issue does not
  block a system switch

### Decryptability Preference

The intended runtime rule is:

```text
Prefer the newest valid identity the host can decrypt over a newer identity it
cannot decrypt.
```

Concrete model:

- signed manifests expose recipient fingerprints as fast prefilters
- followers try decryption only for manifests that target their host age
  recipient
- decrypted plaintext hash must match the manifest
- decrypted private material must derive the public identity in the registry
  event
- if no newer candidate passes, the host keeps the last successfully applied
  private material

Planned local state:

```text
/var/lib/cluster-identity/local-state/
  last-applied/
    HOST/
      SERVICE.json
      SERVICE.private.key
  decryptability-cache.json
```

## Risk Notes

- Placeholder signatures are acceptable only for MVP wiring. Real registry
  trust needs SSH signature verification.
- The SOPS files are encrypted, but they are still high-value Git-tracked
  artifacts. Leader age keys need careful handling.
- Host age key bootstrap is deliberately narrow. Expanding it into general
  private identity copy would undermine the source-ledger model.
- `clusterctl bundle publish` copy/install works over SSH, but hosts that have
  not rebuilt with `system/cluster-identity` may not have
  `cluster-identity-fetch-now.service` yet.
- Do not remove `inventory/host-bootstrap.nix` fallback routes while testing
  live registry deploy resolution.
- Deploying the dendrite should be separate from making the registry the
  preferred deploy target.
