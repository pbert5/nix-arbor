# Registry Operations

Operator playbooks for the live identity registry:

- [`identity-rollout-playbook.md`](./identity-rollout-playbook.md)
- [`identity-registry-troubleshooting.md`](./identity-registry-troubleshooting.md)

Start with `clusterctl identity matrix` when you need a quick service-by-host
view of what the inventory says should exist and what the flake identity source
ledgers still need.

When the missing identities are auto-discoverable, follow it with
`clusterctl identity generate-missing`.
