# Flake-Parts Module Instructions

Apply these rules to `modules/`.

- `modules/flake-parts/` is root flake-parts glue only.
- Do not move real host assembly into `flake.nix`; keep root logic in
  `modules/flake-parts/*.nix` and `lib/*.nix`.
- This repo uses `import-tree` to auto-import active modules under `modules/`.
- If a file under `modules/` should not be auto-imported, place it under a path
  containing `/_`.
- Keep module files explicit and focused. Do not use `default.nix`.
