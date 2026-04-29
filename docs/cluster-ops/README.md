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

- [`architecture.md`](/work/flake/docs/cluster-ops/architecture.md)
  the overall system model, trust boundaries, and file ownership split
- [`command-reference.md`](/work/flake/docs/cluster-ops/command-reference.md)
  what the important commands do and when to reach for them
- [`operator-workflows.md`](/work/flake/docs/cluster-ops/operator-workflows.md)
  the main end-to-end workflows operators actually perform
- [`glossary.md`](/work/flake/docs/cluster-ops/glossary.md)
  the repo-specific terms used throughout this handbook

## Bootstrap And Enrollment

- [`bootstrap-host.md`](/work/flake/docs/cluster-ops/bootstrap-host.md)
  the manual enrollment tool, inputs, outputs, and side effects
- [`bootstrap-state-machine.md`](/work/flake/docs/cluster-ops/bootstrap-state-machine.md)
  the exact lifecycle from raw target to enrolled node
- [`bootstrap-scenarios.md`](/work/flake/docs/cluster-ops/bootstrap-scenarios.md)
  concrete variants for common enrollment situations
- [`peer-enrollment.md`](/work/flake/docs/cluster-ops/peer-enrollment.md)
  how identities become trusted cluster peer metadata

## Deployment And Rollout

- [`deployment-tools.md`](/work/flake/docs/cluster-ops/deployment-tools.md)
  when to use `deploy-rs` vs `colmena`
- [`distributed-builds.md`](/work/flake/docs/cluster-ops/distributed-builds.md)
  how Nix distributed build clients and builders are generated from inventory
- [`fleet-rollout.md`](/work/flake/docs/cluster-ops/fleet-rollout.md)
  rollout patterns for one host, several hosts, or the whole trust graph
- [`transport-switching.md`](/work/flake/docs/cluster-ops/transport-switching.md)
  how a host moves from bootstrap transport to private Ygg transport
- [`deploy-rs-output.md`](/work/flake/docs/cluster-ops/deploy-rs-output.md)
  how to read the generated deploy output and success signals

## Trust And Security

- [`leader-access.md`](/work/flake/docs/cluster-ops/leader-access.md)
  how root deployer access is distributed from trusted leaders
- [`trust-rollout.md`](/work/flake/docs/cluster-ops/trust-rollout.md)
  how new public identity data propagates through the fleet
- [`strict-lockdown.md`](/work/flake/docs/cluster-ops/strict-lockdown.md)
  how to reach the "only explicit peers have contact over Ygg" posture safely

## Inventory And Reference

- [`inventory-surfaces.md`](/work/flake/docs/cluster-ops/inventory-surfaces.md)
  which inventory files own which parts of cluster state
- [`inventory-schema.md`](/work/flake/docs/cluster-ops/inventory-schema.md)
  field-by-field reference for the main operator-facing inventory surfaces
- [`faq.md`](/work/flake/docs/cluster-ops/faq.md)
  short answers to the recurring operational questions
- [`troubleshooting.md`](/work/flake/docs/cluster-ops/troubleshooting.md)
  common failure modes and what to inspect next
