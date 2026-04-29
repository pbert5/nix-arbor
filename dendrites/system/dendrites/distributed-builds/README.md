# `system/distributed-builds`

Inventory-driven Nix distributed build client configuration.

Hosts opt into this dendrite when they should schedule local builds onto other
managed machines. The dendrite reads:

- `host.org.nix.distributedBuilds`
- peer host data from `inventory/hosts.nix`
- bootstrap transport metadata from `inventory/host-bootstrap.nix`
- private Ygg addresses from `inventory/networks.nix`

It sets:

- `nix.distributedBuilds`
- `nix.buildMachines`
- `nix.settings.builders-use-substitutes`

Builder hostnames follow the same practical transport preference as generated
deploy targets: enrolled private Ygg address first when the builder is promoted
to `privateYggdrasil`, then bootstrap target, then inventory endpoint fallback.

Private SSH keys are not stored in the repo. `sshKey` values are local paths on
the coordinator host running the Nix daemon.
