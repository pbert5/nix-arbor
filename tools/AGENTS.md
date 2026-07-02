# Tool Instructions

Apply these rules to repo-owned tools under `tools/`.

- Keep repo-owned CLIs focused and easy to run from the flake.
- When adding or changing a CLI command, update the relevant Navi cheatsheet in
  the same change.
- Repo-specific wrapper scripts always need local cheatsheet coverage because
  upstream cheat repositories will not have them.
- Prefer real runnable command lines in cheatsheets over prose-only reference
  entries.
- Do not run deployment or activation commands from tools unless the user has
  explicitly granted permission for the specific target.
