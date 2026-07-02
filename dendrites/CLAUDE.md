# Dendrites — Navi Cheatsheets and Terminal Usability

## Cheatsheet Placement

When adding or changing a CLI command owned by a dendrite, add or update a
Navi cheatsheet in the **same commit**.

- Place sheets under `cheats/<tool>.cheat` next to the owning dendrite's
  `meta.nix`.
- Set `cheatsheets.fileRegex = "^cheats/.*\\.cheat$";` (or `cheatsheets.files`)
  in that entry's `meta.nix` if not already set.
- `lib/cheatsheets.nix` auto-discovers these and publishes them through
  `dendritic.cheatsheets` for `homes/shared/shell/leaves/navi.nix`.
- `git add` new `cheats/*.cheat` files and their `meta.nix` change before
  evaluating — untracked files are invisible to flake evaluation.

## Where Each Cheat Lives

| Tool type | Cheat location |
|---|---|
| Generic widely-used tool (`git`, `tmux`, `ssh`) | `curatedUpstreamCheats` in `homes/shared/shell/leaves/navi.nix` |
| Tool owned by a dendrite/sub-dendrite | `cheats/<tool>.cheat` under that dendrite |
| Tool configured only under `homes/shared/*` (no owning dendrite) | `dendrites/dev-tools/cheats/` (catch-all) |
| Repo-specific wrapper scripts (`clusterctl`, `codex-switch`, etc.) | Always local, never upstream |

## Variable Providers

For variable choices backed by inventory data (hosts, identity services, plans,
aliases), use Navi variable providers that derive options from the flake or
local runtime state — do not hardcode lists.

## Content Style

Prefer real, runnable command lines over keybinding tables. Navi pastes the
selected entry into the terminal; prose-only reference material (TUI keymaps
etc.) belongs in a `writeShellApplication` help script, not as a Navi entry.
