# Library Instructions

Apply these rules to flake helper code under `lib/`.

- `lib/` owns normalization, registries, assembly, validation, endpoint helpers,
  and inventory-level derivations.
- Keep helpers inert: they should do nothing until imported by assembly or a
  module.
- The entry point for inventory-level derivations is
  `lib/inventory.nix`'s `normalizeInventory`, called once by the flake with the
  entire raw inventory.
- Extend `lib/inventory.nix` or add a focused helper under `lib/` for new
  cross-file derivations, then wire it into `normalizeInventory`.
- Prefer early validation in `lib/validation.nix` when adding new branches,
  fruits, host schema, or inventory surfaces.
- Do not use `default.nix`.
