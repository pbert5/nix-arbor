# `network/yggdrasil-private`

Inventory-driven private Yggdrasil mesh.

## Purpose

Builds the private Ygg overlay from repo inventory and applies the repo's
overlay firewall policy.

## Main Effects

- enables Yggdrasil only on hosts with matching node data
- derives peer URIs from `inventory/networks.nix`
- pins peer public keys in URIs when enrolled
- populates `AllowedPublicKeys`
- emits overlay host aliases when addresses are known
- manages overlay and listener firewall behavior

## Inventory Inputs

- `inventory/networks.nix`
- `inventory/private-yggdrasil-identities.nix`

## Important Notes

- peer public keys live in inventory, not in host-local config
- strict peer-only contact requires enrolled peer `address` and `publicKey`
- service filtering and peering trust are separate concerns

## See Also

- [`docs/private-overlay-and-deployments.md`](/work/flake/docs/private-overlay-and-deployments.md)
- [`docs/cluster-ops/bootstrap-host.md`](/work/flake/docs/cluster-ops/bootstrap-host.md)
