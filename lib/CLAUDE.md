# Lib — Assembly Logic

`lib/` owns all derivation and transformation logic that crosses inventory files.

Typical work that belongs here:
- Deriving leaders/remotes from host roles and network data
- Merging identity service records into network node definitions
- Reading and normalizing key files
- Any cross-file join or transformation

The entry point for inventory-level derivations is `normalizeInventory` in
`lib/inventory.nix`, called once by the flake with the full raw inventory.
When adding new derivations, extend `lib/inventory.nix` or add a focused helper
under `lib/`, then wire it into `normalizeInventory`.

Do not add assembly logic to `inventory/` files; keep them as pure data.
