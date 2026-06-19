# Fish Terminal UX Guide

This document preserves the fish-specific workflow that preceded the shared
zsh profile. It is a reference for restoring or adapting that profile; fish is
not the active login shell in the current inventory.

## Former Fish Profile

The fish profile provided:

- a disabled default greeting for clean startup
- Starship prompt initialization outside VS Code terminals
- fish integrations for fzf, zoxide, Atuin, eza, and yazi
- fish abbreviations for listings and flake operations
- a small interactive guide styled with `gum`

The implementation lived in `homes/shared/shell/leaves/fish.nix` and was
imported by `homes/shared/shell/shell.nix`.

## Interactive Guide

The fish shell exposed the terminal guide through these commands:

- `help` with no topic
- `why`
- `saveme`
- `save-me`

Normal fish help remained available through `help <topic>`.

The first screen showed the tool stack, how to invoke each tool, and what it
was useful for:

1. Fish shell basics and builtins
2. Starship prompt context
3. fzf file, directory, and history search
4. zoxide directory jumping
5. Atuin searchable history
6. eza listings
7. yazi file navigation
8. zellij terminal multiplexing
9. flake rebuild helpers

Pressing `1` through `9` opened a detailed topic, `b` returned to the table,
and `q` exited. `Ctrl+C` and `Ctrl+D` remained immediate escape paths. When
`gum` was unavailable, the guide fell back to plain `printf` output.

## Prompt

The fish profile initialized Starship unless `TERM_PROGRAM` was `vscode`,
where fish and Starship had previously conflicted. The prompt displayed:

- hostname for remote sessions
- current directory
- Git branch and status
- Nix shell context
- duration of slower commands
- non-zero exit status

## Fuzzy Search and Navigation

fzf used `fd` as its source, included hidden files, excluded `.git`, and opened
in a bordered reverse layout.

- `Ctrl+T` searched files.
- `Alt+C` searched directories and changed into the selection.
- `Ctrl+R` searched command history.
- `z <name>` jumped to a frequently visited directory through zoxide.
- `y [path]` opened yazi and returned fish to yazi's final directory on exit.

Examples:

```fish
z flake
z src
y
y ~/src
```

Atuin used fuzzy global search with history sync and update checks disabled.

## Listings and Repo Helpers

Home Manager supplied fish abbreviations for the common eza commands `ls`,
`ll`, `la`, `lt`, and `lla`. Listings included Git status, automatic icons,
directory-first grouping, and a header row.

The repo abbreviations were:

- `ns` — switch the configured host from the flake checkout
- `nb` — build the configured host without switching or creating a result link
- `nf` — show the flake outputs

The checkout defaulted to `${HOME}/flake`, while the target host came from the
active NixOS configuration.

## Remote SSH Compatibility

Generated per-user aliases such as `t320-0-user1` and `r640-0-user1` sent remote
stdin through `sh` without a TTY. This allowed tools such as VS Code Remote-SSH
to send a POSIX bootstrap script even when fish was the login shell.

VS Code required:

```json
"remote.SSH.enableRemoteCommand": true
```

For one-off command-mode SSH, the generated remote command could be bypassed:

```bash
ssh -o RemoteCommand=none t320-0-user1 'hostname && whoami'
```

## Former Rebuild Path

```fish
sudo nixos-rebuild switch --flake /work/flake#desktoptoodle
```

After changing a login shell, a new login session is required. Git flakes also
ignore untracked module files, so a newly created module must be staged in the
correct repository before evaluation depends on it.
