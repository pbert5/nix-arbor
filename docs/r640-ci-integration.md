# r640-0 CI integration and live acceptance

This document records the safe integration checks and the physical-host
acceptance boundary for Nix Arbor #29. The host-specific observations are a
read-only snapshot from 2026-10-15; they are not a deployment authorization or
a claim of live acceptance.

## Integrated software

The integration branch consumes the reviewed provider/build heads:

| Workstream | Reviewed head | Integrated PR |
| --- | --- | --- |
| #25 isolated runner VMs | `208700efed28af0155ec78f42823c2d53983de9c` | [#31](https://github.com/pbert5/nix-arbor/pull/31) |
| #26 private OCI registry | `68991cf4c56df32588352ee6a240aacd15f97afa` | [#30](https://github.com/pbert5/nix-arbor/pull/30) |
| #28 BuildKit image workflow | `d052d7908454772167aa5b3fcb925d418663b405` | [#32](https://github.com/pbert5/nix-arbor/pull/32) |

The integration preserves both `ci-runner-isolation` and
`private-oci-registry` entries in `modules/checks.nix`. The runtime contract
uses isolated guests with their own Docker daemons, private HTTPS registry
reader/writer endpoints, immutable source-SHA image tags and separate
`buildkit/<builder-or-repo>` cache references. Enabled runner inventory now
fails evaluation unless each repository is declared private and its GitHub
`run_workflows_from_fork_pull_requests` setting is verified false. The public
`pbert5/nix-arbor` runner is not eligible; private `meta_bal` and
`simple-evolver` are eligible only while fresh policy reads still match. The
reusable image workflow serializes all source revisions for one caller repo so
they cannot concurrently write its shared `trusted-main` cache tag. Workflow
tests cover these controls; they do not establish live runner, registry, image,
or cache behavior.

The integration review findings RF-01 (untrusted fork jobs could target the
runner labels) and RF-02 (cache writers could race across source revisions)
have producer-owned repairs and independent producer re-reviews at the heads
above. WS-I integration re-review returned `PASS_WITH_FOLLOWUPS` on code head
`ca97d96779bfd8e3e1990bee35c03e3481422f99`; it confirmed these repairs while
leaving RF-03 exact rollback blocked on operator verification. That reviewer
did not independently verify the GitHub setting reads or run tests/builds.
GitHub reports for the two private consumer repos on 2026-10-15 showed fork
pull-request workflows, write tokens, and secrets disabled. Recheck those
settings before enablement; Nix does not continuously monitor policy drift.

## Software verification

On the integration branch, the following passed:

- `nix fmt` after repairs (3 Nix files traversed; no edits)
- `nix flake check --no-update-lock-file` on `x86_64-linux`
- `nix build --no-link .#checks.x86_64-linux.ci-runner-isolation`
- `nix build --no-link .#checks.x86_64-linux.private-oci-registry`
- `nix build --no-link .#nixosConfigurations.r640-0.config.system.build.toplevel`
- `bash tests/ci-image-workflow-contract.sh`
- `bash tests/ci-image-cache-concurrency.sh`
- `git diff --check origin/main...HEAD`

The registry VM derivation completed its isolated guest test. It uses local
test credentials and a local test endpoint; it does not verify Tailscale Serve,
a live certificate, real runtime credentials, host persistence, or a separate
authorized pull client. The runner check validates Nix configuration and
isolation assertions; it does not register a live GitHub runner or execute a
job. The cache-concurrency harness models two different source SHAs sharing
the repository lock and cache reference; it does not exercise GitHub's live
scheduler. GitHub concurrency may replace an older pending run with a newer
one, so an intermediate source SHA must be dispatched manually if required.

## Read-only host snapshot

The session ran on physical `r640-0`. At the time of inspection:

- virtualization flag `vmx` was present; 56 CPUs and 188 GiB RAM were visible,
  with 119 GiB available;
- ZFS pool `mypool` was `ONLINE`, 952 GiB total with 632 GiB free;
- `/mypool/docker_data` was a mounted ZFS dataset and Docker reported it as its
  data root; Docker was active with 74 containers (43 running) and 2063 images;
- Docker, Tailscale, and SSH services were active; Tailscale Serve had no
  configured handlers;
- `nix.settings.build-dir` was `/mypool/nix-build`;
- `sudo -n id -u` failed with `sudo: a password is required`;
- `/run/current-system` resolved to
  `/nix/store/k4dhhaif4k32gpljlpg9r88x4k7vfjh7-nixos-system-r640-0-26.11.20260928.7a0f122`,
  while `/nix/var/nix/profiles/system` pointed at generation 183,
  `/nix/store/xjri1w2667c1j958qg1nyhzynfkks2aj-nixos-system-r640-0-26.11.20260911.eaad089`;
- listing generations through `nix-env` was denied by the profile lock.

The running system and current boot profile therefore differ. A privileged
operator must identify the intended known-good generation and verify an exact
rollback procedure before any host activation. The available read-only
evidence is insufficient to claim rollback readiness.

## Live acceptance boundary

No host configuration, ZFS state, Docker state, network, credential, or live
service was changed. No GitHub runner was registered; no trusted workflow was
run on the host; no image was pushed or pulled; no BuildKit second-build cache
measurement was made. `R640_CI_READY` must remain unset, and consumer opt-in
lanes and runtime secrets must remain disabled/unset.

Before live acceptance, an authorized operator must:

1. Provide the permitted privileged operator session and identify the exact
   known-good generation, given the current `/run/current-system` versus system
   profile mismatch.
2. Confirm the management/recovery path and a tested exact-generation rollback
   plan before any `nixos-rebuild test` or `switch`.
3. Confirm Tailscale DNS/ACL and HTTPS certificate readiness for the approved
   registry endpoint; keep it within the private trust domain.
4. Provision scoped runner-registration and separate registry reader/writer
   credentials through the approved runtime-only secret mechanism. Do not put
   credential values in Nix expressions, logs, issue comments, or this
   repository.
5. Re-run current storage, service, resource, and generation preflight, then
   authorize the narrow single-VM/single-job acceptance window.
6. Record the exact GitHub run/job and guest runner identity; test unauthenticated
   and wrong-role denial over verified HTTPS; build a tracked image at an exact
   source SHA; record its OCI digest and platform; pull that digest from a
   separate authorized client without rebuilding; measure a second-build
   BuildKit cache hit; inspect logs/layers/cache for secret leakage; measure
   resource and retention/GC behavior; verify restart and ephemeral
   re-registration; and exercise the approved rollback while confirming
   existing services remain intact.

Until these actions are completed and their evidence is attached to #29, the
platform is implemented and locally tested but live acceptance remains
blocked. Missing live credentials or operator authority does not invalidate
the software checks above.
