# Terminal UX Guide

The shared Home Manager workstation profile provides a zsh-first terminal
stack for both `user1` and `user2` on every managed host.

The previous fish workflow and its interactive terminal guide are preserved in
[Fish Terminal UX](./fish-terminal-ux.md).

## What Is Enabled

- `zsh` is the login and interactive shell.
- Home Manager enables completion, autosuggestions, syntax highlighting, and
  history substring search.
- Oh My Zsh supplies the `colored-man-pages`, `command-not-found`, `dirhistory`,
  `extract`, `git`, and `sudo` plugins. Starship remains the prompt, so Oh My
  Zsh does not select a theme.
- `fzf` provides fuzzy file, directory, and history search.
- `zoxide` provides smart directory jumping.
- `atuin` provides searchable, local-only shell history.
- `eza`, `yazi`, and `zellij` provide listings, file navigation, and terminal
  multiplexing respectively.

The configuration follows the split recommended by the
[Official NixOS Wiki](https://wiki.nixos.org/wiki/Zsh): NixOS enables zsh and
makes it the account shell, while Home Manager owns interactive configuration
and plugins.

## Ownership

- `dendrites/base/leaves/terminal.nix` enables zsh system-wide, including
  vendor completions and registration in `/etc/shells`.
- `inventory/users.nix` selects `zsh` as each normal user's login shell.
- `homes/shared/shell/shell.nix` assembles the interactive shell leaves.
- `homes/shared/shell/leaves/zsh.nix` owns zsh behavior and plugins.
- The remaining leaves own Starship, fzf, zoxide, Atuin, and repo aliases.
- `homes/shared/tui/tui.nix` owns eza, yazi, and zellij.

## Related Workstation Behavior

- `nixard` is installed on hosts selecting `system/workstation`; run `nixard`
  and press `u` on first use to populate its local package database.
- On `t320-0`, the host override configures btop to discover mounted filesystems
  so `/big` and `/fast` appear alongside `/` and `/boot`.
- Both users receive `big` and `fast` home-directory links on `t320-0`.
- The repo overlay teaches btop to read ZFS space from `zfs list`; `statvfs`
  otherwise reports the root dataset reference size rather than whole-pool use.

## Daily Usage

The prompt shows the remote hostname, current directory, Git state, Nix shell
context, slow-command duration, and non-zero exit status.

Useful keys and commands:

- `Tab` opens completion; matching is case-insensitive.
- Up and Down search history for the text already entered.
- `Ctrl+T` fuzzy-finds files, `Alt+C` fuzzy-finds directories, and `Ctrl+R`
  opens Atuin history search.
- `z <name>` jumps to a frequently visited directory.
- `y [path]` opens yazi and returns to its final directory on exit.
- `ls`, `ll`, `la`, `lt`, and `lla` use eza's zsh integration.

History is stored at `$XDG_DATA_HOME/zsh/history`, shared between concurrent
shells, deduplicated, and capped at 100,000 entries. Atuin sync and update
checks remain disabled.

## Repo Helpers

- `ns` switches the configured host from the flake checkout.
- `nb` builds that host without switching or creating a result symlink.
- `nf` shows the flake outputs.

By default the checkout is `${HOME}/flake`, and the host comes from the active
NixOS configuration. Override `flakeTarget.path` in Home Manager when needed.

## Rebuild Path

```zsh
sudo nixos-rebuild switch --flake /work/flake#desktoptoodle
```

Re-login after switching so the new login shell takes effect. If evaluation
cannot see a newly created module, stage only that file first; Git flakes ignore
untracked files.
