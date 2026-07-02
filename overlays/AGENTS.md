# Overlay Instructions

Apply these rules to overlays under `overlays/`.

- Keep overlays narrow and predictable.
- Prefer package-local fixes or normal package definitions before global
  overlays.
- Document why an overlay exists when the reason is not obvious from the code.
- Build at least one affected consumer when practical.
- Do not use `default.nix`.
