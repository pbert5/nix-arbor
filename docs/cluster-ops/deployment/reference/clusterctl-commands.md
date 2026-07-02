# `clusterctl` Command Inventory

This is the flat command inventory for the `clusterctl` component. It is
intentionally redundant with workflow documentation so command discovery does
not depend on reading an operational narrative.

## Operator Commands

- `clusterctl deploy HOST [HOST ...]`
- `clusterctl update [INPUT ...]`
- `clusterctl registry validate` # broken
- `clusterctl registry notify`
- `clusterctl registry status [--node HOST]`
- `clusterctl identity matrix`
- `clusterctl identity generate-missing`
- `clusterctl identity publish`
- `clusterctl identity promote NODE SERVICE`
- `clusterctl identity burn NODE SERVICE`
- `clusterctl identity smoke-test`
- `clusterctl bundle seal NODE SERVICE`
- `clusterctl receipt write`
- `clusterctl receipt collect NODE SERVICE`
- `clusterctl host-age bootstrap HOST`
- `clusterctl host-age public HOST`

## Internal System Plumbing

These commands are called by NixOS activation or systemd units. Operators
normally inspect their services rather than invoking them directly.

- `clusterctl registry ensure-v1`
- `clusterctl registry fetch-ipfs`
- `clusterctl registry snapshot`
- `clusterctl registry publish-ipfs`
- `clusterctl registry ipns-key ensure`

## Emergency Repair Commands

These commands deliberately bypass or rebuild part of the normal declarative
flow. Use them only with an identified failure and record what was repaired.

- `clusterctl registry reconcile`
- `clusterctl bundle emergency-publish NODE SERVICE`
- `clusterctl host-age rotate HOST`

`bundle emergency-publish` copies plaintext private material over SSH. The
normal private-delivery path is `bundle seal`.

## Development Primitives

Raw single-event publication remains an internal Python implementation helper
for tests. It is intentionally not exposed through the installed CLI.

## Retired Commands

The following commands are no longer available:

- `registry init` — replaced by activation-owned `registry ensure-v1`
- `registry materialize` — reconciliation and fetching materialize verified state
- `registry sync`, `registry push`, `registry remotes sync` — retired Git transport
- `registry resign-placeholders` — completed one-time migration
- `identity publish-inventory` — replaced by `identity publish`
- `identity status` — merged into `registry status`
- `identity apply` — fetch and reconciliation apply state automatically
- `bundle publish` — renamed to `bundle emergency-publish`
- `vm` — use the dedicated `nix run .#host-vm -- HOST` app
