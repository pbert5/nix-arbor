# Fruit Instructions

Apply these rules to deployable outcomes under `fruits/`.

- A fruit is a named, deployable, long-running outcome that may require
  dendrites and add concrete service defaults.
- Fruit entrypoints use explicit filenames matching their directory names, such
  as `fruits/fossilsafe/fossilsafe.nix`.
- Fruits require `meta.nix`. Metadata should describe runtime kind,
  persistence, ports, required dendrites, maturity, and cheatsheets when
  relevant.
- Keep reusable capability behavior in `dendrites/`; keep named deployable
  outcomes here.
- Do not use `default.nix`.
- When a fruit exposes a repo-specific CLI, add or update a local Navi
  cheatsheet and expose it through fruit metadata.
