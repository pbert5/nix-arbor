# Dendrite Instructions

Apply these rules to reusable NixOS capability branches under `dendrites/`.

- A dendrite is a reusable capability family such as `base`, `desktop`,
  `media`, `network`, `storage`, or `system`.
- A sub-dendrite is a child specialization such as `desktop/gnome` or
  `storage/zfs`.
- A leaf is a small active internal behavior module imported explicitly by a
  dendrite entrypoint. Leaves are usually not selected directly by hosts.
- Dendrite and sub-dendrite entrypoints use explicit filenames matching their
  directory names, such as `dendrites/storage/storage.nix`.
- Dendrites require `meta.nix`. Metadata describes discovery, dependencies,
  conflicts, maturity, docs, and cheatsheets; it must not hide module bodies or
  host-specific behavior.
- Compose local leaves with explicit imports inside the entrypoint. Do not add
  branch-local auto-loading that makes helper files active just because they
  exist.
- Do not use `default.nix`.

## Cheatsheets

- When adding or changing a repo-owned CLI command from a dendrite, update or
  add a Navi cheatsheet under the owning dendrite's `cheats/` directory.
- Expose local sheets through `meta.cheatsheets` using `fileRegex` or explicit
  `files`.
- Use variable providers derived from the flake or local runtime state instead
  of hardcoded host, service, alias, or plan lists.
