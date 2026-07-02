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
- HyFetch runs Fastfetch at interactive zsh startup and applies its transgender
  pride gradient to Fastfetch's built-in NixOS logo. The `Cluster` row checks
  `systemctl is-system-running` on every exported host in parallel and
  summarizes healthy, degraded, and unreachable machines in green, yellow, and
  red respectively. Set `FASTFETCH_DISABLE=1` before launching zsh to skip it.
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
- The remaining leaves own Starship, fzf, zoxide, Atuin, HyFetch/Fastfetch, and
  repo aliases.
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

- `ns` safely rebuilds the configured host from the flake checkout. It switches
  same-release changes live, but installs cross-release changes with
  `nixos-rebuild boot` and asks for a reboot so old and new desktop/systemd
  components are not mixed in one session. Build progress is rendered through
  `nom`, with full build logs shown alongside its live dependency tree. Internal
  `nixos-rebuild-ng` debug tracing is filtered from the display. Authentication
  happens before output enters the `nom` pipeline, keeping password input on the
  terminal.
- `nsh` provides the same release-safe behavior through `nh`, which uses `nom`
  for build progress.
- `nb` builds that host without switching or creating a result symlink.
- `nf` shows the flake outputs.

By default the checkout is `${HOME}/flake`, and the host comes from the active
NixOS configuration. Override `flakeTarget.path` in Home Manager when needed.

## Corrupt History File Recovery

If zsh reports `corrupt history file` at startup, the file has embedded null
bytes — this happens when a `nixos-rebuild switch` is interrupted mid-session
while zsh is writing history.

```zsh
# Back up, then strip null bytes in-place
cp ~/.local/share/zsh/history ~/.local/share/zsh/history.bak
python3 -c "
import sys
data = open('$HOME/.local/share/zsh/history', 'rb').read()
open('$HOME/.local/share/zsh/history', 'wb').write(data.replace(b'\x00', b''))
"
```

Open a new shell to pick up the cleaned file. The backup can be deleted once
zsh stops complaining.

## Rebuild Path

For normal same-release changes, run `ns`. During a NixOS release upgrade, `ns`
installs the new boot generation without activating it live; reboot afterward.

The equivalent explicit release-upgrade commands are:

```zsh
sudo nixos-rebuild boot --flake /work/flake#desktoptoodle
sudo systemctl reboot
```

Re-login after switching so the new login shell takes effect. If evaluation
cannot see a newly created module, stage only that file first; Git flakes ignore
untracked files.
