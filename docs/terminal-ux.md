# Terminal UX Guide

This repo now manages a shared fish-first Home Manager terminal stack assembled
from the dendritic flake and used by both `user1` and `user2`.

## What Is Enabled

- `fish` is the intended login shell.
- `starship` provides the prompt.
- `fzf` provides fuzzy file, directory, and history search.
- `zoxide` provides smart directory jumping.
- `atuin` provides searchable shell history.
- `eza` replaces common `ls` workflows.
- `yazi` is the terminal file manager and launcher wrapper.
- `zellij` remains enabled as the terminal multiplexer currently in use.
- `gum` is available for lightweight shell UI and powers the quick terminal guide.

## Ownership

- NixOS owns shell availability and each user's login shell.
- Home Manager branches under `homes/` own interactive shell behavior,
  prompt config, aliases, search, history tools, and terminal UI tooling.
- `inventory/users.nix` owns low-risk per-user identity and user-specific
  config facts.
- `lib/users.nix` renders those facts into NixOS and Home Manager user modules
  during assembly.

Relevant files:

- `dendrites/base/leaves/terminal.nix`
- `dendrites/system/dendrites/workstation/workstation.nix`
- `homes/shared/shell/shell.nix`
- `homes/shared/shell/leaves/fish.nix`
- `homes/shared/shell/leaves/starship.nix`
- `homes/shared/shell/leaves/fzf.nix`
- `homes/shared/shell/leaves/zoxide.nix`
- `homes/shared/shell/leaves/atuin.nix`
- `homes/shared/shell/leaves/terminal-aliases.nix`
- `homes/shared/tui/tui.nix`
- `homes/shared/workstation/workstation.nix`
- `inventory/users.nix`
- `lib/users.nix`

## Daily Usage

### Fish

- New interactive shells should start in `fish`.
- The default fish greeting is disabled to keep startup clean.
- Fish abbreviations are preferred over raw aliases where that fits the workflow.
- `help` with no topic opens the interactive terminal guide.
- `help <topic>` still opens normal fish help.
- `why`, `saveme`, and `save-me` also open the guide.

### Interactive Guide

The shell includes a small interactive guide for the terminal tool stack.

- Open it with `help`, `why`, `saveme`, or `save-me`.
- The first screen shows a numbered table with the high-level tools, how to call
  them, and what each one is for.
- Press `1` through `9` to drill into a tool, `b` to go back, `q` to quit, or
  use `Ctrl+C` / `Ctrl+D` to escape immediately.
- `gum` provides the styling for the interface.

### Prompt

The prompt is intentionally compact and shows:

- hostname when connected remotely
- current directory
- git branch and status
- nix shell context
- command duration for slower commands
- command exit status when non-zero

### Fuzzy Search With `fzf`

`fzf` is configured to use `fd` for file and directory discovery.

- `Ctrl+T` searches files.
- `Alt+C` searches directories and changes into the selected one.
- `Ctrl+R` searches command history.

Defaults:

- hidden files are included
- `.git` is excluded from the search source
- the picker opens with a bordered reverse layout

### Directory Jumping With `zoxide`

Use `z` to jump to directories you visit often.

Examples:

```fish
z flake
z src
```

### History With `atuin`

`atuin` is enabled with fish integration and starts local-only.

- history sync is currently disabled
- update checks are disabled
- search mode is fuzzy

In practice, use the Atuin history workflow instead of relying only on plain
shell history scrolling.

### Listings With `eza`

Common listings are available through fish abbreviations created by Home Manager.

- `ls`
- `ll`
- `la`
- `lt`
- `lla`

The current `eza` setup enables git status, icons when supported, grouped
directories first, and a header row.

### File Navigation With `yazi`

Use `y` to open `yazi`.

```fish
y
y ~/src
```

The wrapper updates the current shell directory when you exit `yazi`, so it can
be used as an actual navigation tool instead of just a viewer.

## Repo Helpers

These fish abbreviations are configured:

- `ns` expands to `sudo nixos-rebuild switch --flake <path>#<host>`
- `nb` expands to `nix build <path>#nixosConfigurations.<host>.config.system.build.toplevel --no-link`
- `nf` expands to `nix flake show <path>`

By default, `<path>` is `${HOME}/flake` and `<host>` comes from the active NixOS
host. Override `flakeTarget.path` in a user's Home Manager config when the flake
checkout lives elsewhere.

## Rebuild Path

The intended rebuild path remains the top-level flake:

```fish
sudo nixos-rebuild switch --flake /work/flake#dev-machine
```

After rebuild, open a new shell session or re-login to pick up login-shell
changes cleanly.

## Troubleshooting

- If a new terminal still opens in Bash, confirm the system was rebuilt and the
  session was re-opened after `user1`'s login shell changed to fish.
- If a flake evaluation says a new module file does not exist, check whether the
  file is untracked in Git. This repo is evaluated as a Git flake source.
- If a tool feels like it belongs at OS scope instead of user scope, prefer
  keeping the user UX in Home Manager unless the tool must exist system-wide.
