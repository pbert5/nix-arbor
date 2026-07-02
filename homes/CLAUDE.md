# Homes — Home Manager Configurations

## Build Verification

After any change under `homes/`, verify with a build before reporting done:

```bash
rtk nixos-rebuild build --flake .#desktoptoodle
```

This exercises the Home Manager activation for the primary user on
`desktoptoodle`. Do not report success until the build passes.

## Navi Cheatsheets

Tools that are configured only under `homes/shared/*` with no owning dendrite
(e.g. `claude-code`, `podman`, `zoxide`, `yazi`, zsh aliases) have no path
through `lib/cheatsheets.nix`. Their cheat files belong in
`dendrites/dev-tools/cheats/`, matching the existing `codex-switch.cheat`
precedent.

## Scoped Note on `modules/`

`homes/` modules that live under `modules/` are auto-imported via `import-tree`.
Files that must not be auto-imported must live under a path containing `/_`.
