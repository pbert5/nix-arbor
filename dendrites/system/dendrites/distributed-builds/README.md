# `system/distributed-builds`

Inventory-driven Nix distributed build client configuration.

Hosts opt into this dendrite when they should schedule local builds onto other
managed machines. The dendrite reads:

- `host.org.nix.distributedBuilds`
- peer host data from `inventory/hosts.nix`
- bootstrap transport metadata from `inventory/host-bootstrap.nix`
- the normalized leader signing/transport key from `inventory.identityPolicy`
- private Ygg addresses from `inventory/networks.nix`

It sets:

- `nix.distributedBuilds`
- `nix.buildMachines`
- `nix.settings.builders-use-substitutes`

Builder hostnames follow the same practical transport preference as generated
deploy targets: enrolled private Ygg address first when the builder is promoted
to `privateYggdrasil`, then bootstrap target, then inventory endpoint fallback.

Private SSH keys are not stored in the repo. Leader coordinators prefer the
SOPS-installed `cluster-identity-leader-user-ssh-nix-build` key because it is
readable by the root-owned Nix remote build hook. Other coordinators normally
reuse their normalized registry transport/signing key, with bootstrap transport
metadata as the fallback. `org.nix.distributedBuilds.sshKey` and per-builder
`sshKey` remain explicit local-path overrides and must be readable by the Nix
daemon's remote build hook.
