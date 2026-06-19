# Cluster Ops

This folder is the operator handbook for the repo's cluster lifecycle:
bootstrap, identity enrollment, trust rollout, transport switching, and normal
fleet deployment.

The current operating model is intentionally two-layer:

1. bootstrap a host from a trusted leader over a raw management path
2. switch normal operations to inventory-driven deployment over private Ygg

The current trusted leaders are:

- `desktoptoodle`
- `r640-0`

## Start Here

Read these first if you are getting oriented:

- [`architecture.md`](/work/flake/docs/cluster-ops/start/architecture.md)
  the overall system model, trust boundaries, and file ownership split
- [`../../bootstrap/README.md`](/work/flake/bootstrap/README.md)
  tool-local bootstrap docs, validator usage, and secret-management notes
- [`live-installer.md`](/work/flake/docs/cluster-ops/bootstrap/live-installer.md)
  how to build the SSH-enabled live installer and what it guarantees
- [`new-host-from-live-installer.md`](/work/flake/docs/cluster-ops/bootstrap/new-host-from-live-installer.md)
  the step-by-step playbook for bringing up a host from the USB image
- [`nbootstrap.md`](/work/flake/docs/cluster-ops/bootstrap/nbootstrap.md)
  the umbrella CLI and when to prefer it over the lower-level tools
- [`clusterctl-quick-reference.md`](/work/flake/docs/cluster-ops/reference/clusterctl-quick-reference.md)
  the shortest entry point for `deploy`, `identity matrix`, and
  `identity generate-missing`
- [`command-reference.md`](/work/flake/docs/cluster-ops/reference/command-reference.md)
  what the important commands do and when to reach for them
- [`operator-workflows.md`](/work/flake/docs/cluster-ops/start/operator-workflows.md)
  the main end-to-end workflows operators actually perform
- [`glossary.md`](/work/flake/docs/cluster-ops/reference/glossary.md)
  the repo-specific terms used throughout this handbook

## Bootstrap And Enrollment

- [`live-installer.md`](/work/flake/docs/cluster-ops/bootstrap/live-installer.md)
  build and use the SSH-ready live installer image
- [`new-host-from-live-installer.md`](/work/flake/docs/cluster-ops/bootstrap/new-host-from-live-installer.md)
  the hand-held playbook for a brand-new target
- [`nbootstrap.md`](/work/flake/docs/cluster-ops/bootstrap/nbootstrap.md)
  the single entrypoint that wraps the common bootstrap tasks
- [`bootstrap-host.md`](/work/flake/docs/cluster-ops/bootstrap/enrollment/bootstrap-host.md)
  the manual enrollment tool, inputs, outputs, and side effects
- [`bootstrap-state-machine.md`](/work/flake/docs/cluster-ops/bootstrap/enrollment/state-machine.md)
  the exact lifecycle from raw target to enrolled node
- [`bootstrap-scenarios.md`](/work/flake/docs/cluster-ops/bootstrap/enrollment/scenarios/bootstrap-scenarios.md)
  concrete variants for common enrollment situations
- [`peer-enrollment.md`](/work/flake/docs/cluster-ops/bootstrap/enrollment/peer-enrollment.md)
  how identities become trusted cluster peer metadata

## Deployment And Rollout

- [`deployment-tools.md`](/work/flake/docs/cluster-ops/deployment/tools.md)
  when to use `clusterctl deploy`, `deploy-rs`, and `colmena`
- [`distributed-builds.md`](/work/flake/docs/cluster-ops/deployment/reference/distributed-builds.md)
  how Nix distributed build clients and builders are generated from inventory
- [`fleet-rollout.md`](/work/flake/docs/cluster-ops/deployment/fleet-rollout.md)
  rollout patterns for one host, several hosts, or the whole trust graph
- [`transport-switching.md`](/work/flake/docs/cluster-ops/deployment/transport-switching.md)
  how a host moves from bootstrap transport to private Ygg transport
- [`clusterctl.md`](/work/flake/docs/cluster-ops/deployment/reference/clusterctl.md)
  full `clusterctl` command groups, deploy flags, and related identity/registry options
- [`deploy-rs-output.md`](/work/flake/docs/cluster-ops/deployment/reference/deploy-rs-output.md)
  how to read the generated deploy output and success signals
- [`identity/README.md`](/work/flake/docs/cluster-ops/identity/README.md)
  live cluster identity registry docs, transport notes, rollout playbooks, and
  repair flows

## Trust And Security

- [`leader-access.md`](/work/flake/docs/cluster-ops/trust/leader-access.md)
  how root deployer access is distributed from trusted leaders
- [`trust-rollout.md`](/work/flake/docs/cluster-ops/trust/trust-rollout.md)
  how new public identity data propagates through the fleet
- [`strict-lockdown.md`](/work/flake/docs/cluster-ops/trust/strict-lockdown.md)
  how to reach the "only explicit peers have contact over Ygg" posture safely
- [`identity/operations/identity-registry-troubleshooting.md`](/work/flake/docs/cluster-ops/identity/operations/identity-registry-troubleshooting.md)
  live identity registry failure modes and exact inspection commands

## Inventory And Reference

- [`inventory-surfaces.md`](/work/flake/docs/cluster-ops/inventory/surfaces.md)
  which inventory files own which parts of cluster state
- [`inventory-schema.md`](/work/flake/docs/cluster-ops/inventory/schema.md)
  field-by-field reference for the main operator-facing inventory surfaces
- [`faq.md`](/work/flake/docs/cluster-ops/start/faq.md)
  short answers to the recurring operational questions
- [`troubleshooting.md`](/work/flake/docs/cluster-ops/reference/troubleshooting.md)
  common failure modes and what to inspect next
