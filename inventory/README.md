# Public Inventory

The public mirror keeps the main `inventory/` surface intentionally simple.

At the root you get a small, readable inventory that is easy to learn from:

- `users.nix`
- `hosts.nix`
- `networks.nix`
- `storage-fabric.nix`

When you want to see how the same schema grows to cover a more involved setup,
look in `./complex/`.

The `complex/` subfolder keeps richer examples for things like:

- annex
- SeaweedFS
- Radicle
- tape-backed archive nodes

That way the public flake has a straightforward default inventory, while still
preserving more advanced host examples nearby.
