{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.flakeTarget;
  safeRebuild = pkgs.writeShellApplication {
    name = "nixos-safe-rebuild";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.gnused
      pkgs.nix-output-monitor
    ];
    text = ''
      flake_target="${cfg.path}#${cfg.hostName}"
      release_attr="${cfg.path}#nixosConfigurations.${cfg.hostName}.config.system.nixos.release"
      release_family() {
        local release="$1"
        if [[ "$release" =~ ^([0-9]+\.[0-9]+) ]]; then
          printf '%s\n' "''${BASH_REMATCH[1]}"
        else
          printf '%s\n' "$release"
        fi
      }

      current_release="$(nixos-version)"
      target_release="$(nix eval --raw --option warn-dirty false "$release_attr")"
      current_release_family="$(release_family "$current_release")"
      target_release_family="$(release_family "$target_release")"

      rebuild() {
        sudo -v
        sudo -n nixos-rebuild "$@" --flake "$flake_target" --log-format internal-json --print-build-logs -v \
          |& sed -u '/^debug: nixos_rebuild\./d' \
          | nom --json
      }

      if [[ "$current_release_family" != "$target_release_family" ]]; then
        echo "NixOS release transition: $current_release -> $target_release"
        echo "Installing the new generation for boot; live switching across releases can break the desktop session."
        rebuild boot
        echo "Generation installed. Reboot to enter NixOS $target_release."
      else
        rebuild switch
      fi
    '';
  };
  safeTestRebuild = pkgs.writeShellApplication {
    name = "nixos-safe-test-rebuild";
    runtimeInputs = [
      pkgs.gnused
      pkgs.nix-output-monitor
    ];
    text = ''
      flake_target="${cfg.path}#${cfg.hostName}"
      sudo -v
      sudo -n nixos-rebuild test --flake "$flake_target" --log-format internal-json --print-build-logs -v \
        |& sed -u '/^debug: nixos_rebuild\./d' \
        | nom --json
    '';
  };
  safeNhRebuild = pkgs.writeShellApplication {
    name = "nixos-safe-nh-rebuild";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.nh
    ];
    text = ''
      flake_target="${cfg.path}#${cfg.hostName}"
      release_attr="${cfg.path}#nixosConfigurations.${cfg.hostName}.config.system.nixos.release"
      release_family() {
        local release="$1"
        if [[ "$release" =~ ^([0-9]+\.[0-9]+) ]]; then
          printf '%s\n' "''${BASH_REMATCH[1]}"
        else
          printf '%s\n' "$release"
        fi
      }

      current_release="$(nixos-version)"
      target_release="$(nix eval --raw --option warn-dirty false "$release_attr")"
      current_release_family="$(release_family "$current_release")"
      target_release_family="$(release_family "$target_release")"

      if [[ "$current_release_family" != "$target_release_family" ]]; then
        echo "NixOS release transition: $current_release -> $target_release"
        echo "Installing the new generation for boot; live switching across releases can break the desktop session."
        nh os boot "$flake_target"
        echo "Generation installed. Reboot to enter NixOS $target_release."
      else
        nh os switch "$flake_target"
      fi
    '';
  };
  tmuxHelper = pkgs.writeShellApplication {
    name = "mux";
    text = ''
      cat <<'EOF'
      tmux helper

      Shortcut:
        mox
          Attach to the main session, or create it if it does not exist.
          Runs: tmux new -A -s main

      Sessions:
        tmux ls
          List sessions.

        tmux new -s work
          Create a new session named work.

        tmux new -A -s work
          Attach to work, or create it if it does not exist.

        tmux attach -t work
          Attach to an existing session named work.

        tmux kill-session -t work
          Kill the session named work.

      Inside tmux:
        Ctrl-b c
          Create a window.

        Ctrl-b n / Ctrl-b p
          Move to the next or previous window.

        Ctrl-b %
          Split the current pane vertically.

        Ctrl-b "
          Split the current pane horizontally.

        Ctrl-b d
          Detach from the current session.
      EOF
    '';
  };
in
{
  home.packages = [ tmuxHelper ];

  programs.zsh.shellAliases = {
    mox = "tmux new -A -s main";
    ns = lib.getExe safeRebuild;
    nt = lib.getExe safeTestRebuild;
    nsh = lib.getExe safeNhRebuild;
    nb = "nix build ${cfg.path}#nixosConfigurations.${cfg.hostName}.config.system.build.toplevel --no-link";
    nf = "nix flake show ${cfg.path}";
  };
}
