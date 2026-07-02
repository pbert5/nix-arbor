# Inventory — Data Only

`inventory/` is **pure data**. Assembly logic does not belong here.

Prohibited inside inventory files:
- Derivations that span multiple sources
- `builtins.readFile` for key material
- Dynamic URL construction
- Filtering or mapping that joins inventory files across each other

All service/listener ports used by the flake (localhost-only, private
overlay-only, experimental, reserved) must be declared in `inventory/ports.nix`.

Assembly logic belongs in `lib/`. The entry point for inventory-level
derivations is `lib/inventory.nix`'s `normalizeInventory`, called once by the
flake with the entire raw inventory. Extend `lib/inventory.nix` or add a
focused helper under `lib/` for new derivations, then wire into
`normalizeInventory`.
