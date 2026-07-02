# Check Instructions

Apply these rules to flake checks under `checks/`.

- Keep checks focused on behavior that should fail fast during evaluation.
- Prefer checks that exercise the changed derivation or validation boundary.
- Newly created check files must be Git-tracked before flake evaluation can see
  them.
- Do not use `default.nix`.
