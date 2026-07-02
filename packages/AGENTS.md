# Package Instructions

Apply these rules to package definitions under `packages/`.

- Keep package definitions small and explicit.
- Prefer Nix-native packaging patterns and existing repo helpers before adding
  new abstractions.
- For Python embedded in Nix writers, remember builders may enforce flake8 with
  a 79-character line limit.
- Build the affected package before handoff when practical.
- Do not use `default.nix`.
