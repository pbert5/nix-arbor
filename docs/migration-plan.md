# Migration Notes

This is no longer the initial migration checklist. It is now a short note about
what changed and what still looks like follow-up work.

## Already Landed

- Thin root `flake.nix`
- `modules/flake-parts/` glue
- passive registries for `dendrites/`, `fruits/`, `homes/`, and `hosts/`
- normalized host schema with `facts`, `org`, and `overrides`
- required metadata for dendrites and fruits
- composition validation
- `default.nix` ban

## Remaining Drift

- Some planning notes still assume a future root that exposes more composition
  directly from `flake.nix`. The current code still intentionally uses
  `flake-parts`.
- Some host override logic can likely move into reusable dendrites over time,
  but that should be done case by case rather than by forcing hosts to become
  unrealistically tiny.
- Fruit coverage is still sparse today. The architecture supports more fruits
  than the repo currently defines.

## Read Instead

- Overview:
  [`docs/architecture.md`](/work/flake/docs/architecture.md)
- Plain-English guide:
  [`docs/dendritic-guide.md`](/work/flake/docs/dendritic-guide.md)
- Authoring guide:
  [`docs/authoring-guide.md`](/work/flake/docs/authoring-guide.md)
