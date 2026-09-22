_: {
  perSystem =
    { pkgs, ... }:
    let
      cheats = ../cheats;
      help = pkgs.writeShellApplication {
        name = "nix-arbor-help";
        runtimeInputs = [ pkgs.navi ];
        text = ''
          exec navi --path "${cheats}''${NAVI_PATH:+:$NAVI_PATH}"
        '';
      };
      local = pkgs.writeShellApplication {
        name = "nix-arbor-local";
        runtimeInputs = [
          pkgs.coreutils
          pkgs.git
          pkgs.jq
          pkgs.nix
        ];
        text = ''
                    set -euo pipefail

                    operation="''${1:-}"
                    if [[ -n "$operation" ]]; then
                      shift
                    fi

                    repository_root="''${NIX_ARBOR_ROOT:-}"
                    if [[ -z "$repository_root" ]]; then
                      repository_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
                    fi
                    if [[ -z "$repository_root" || ! -f "$repository_root/flake.nix" ]]; then
                      printf '%s\n' "nix-arbor-local must run from the Nix Arbor checkout (or with NIX_ARBOR_ROOT set)." >&2
                      exit 1
                    fi
                    cd "$repository_root"

          # Keep the input-to-checkout mapping in this one small, declarative
          # location. Add future checked-out components beside AshZsh.
          declare -a overrides=()
          collect_overrides() {
            local index component_input component_local_path component_checkout
            local -a component_inputs=(ashzsh ashes-tools ashes-desktop-apps tilingDesktop arbor-manager arbor-registry)
            local -a component_paths=(packages/AshZsh packages/AshesTools packages/AshDesktopApps packages/tiling-desktop packages/arbor-manager packages/arbor-registry)
            for index in "''${!component_inputs[@]}"; do
              component_input="''${component_inputs[$index]}"
              component_local_path="''${component_paths[$index]}"
              component_checkout="$repository_root/$component_local_path"
              if [[ -f "$component_checkout/flake.nix" ]]; then
                overrides+=(--override-input "$component_input" "path:$component_checkout")
              fi
            done
          }

                    print_overrides() {
            printf '%s\n' "Local flake overrides:"
            local index component_input component_local_path component_checkout
            local -a component_inputs=(ashzsh ashes-tools ashes-desktop-apps tilingDesktop arbor-manager arbor-registry)
            local -a component_paths=(packages/AshZsh packages/AshesTools packages/AshDesktopApps packages/tiling-desktop packages/arbor-manager packages/arbor-registry)
            local -a component_remotes=(github:pbert5/AshZsh github:pbert5/AshesTools github:pbert5/AshDesktopApps github:pbert5/TilingDesktop github:pbert5/arbor-manager github:pbert5/arbor-registry)
            for index in "''${!component_inputs[@]}"; do
              component_input="''${component_inputs[$index]}"
              component_local_path="''${component_paths[$index]}"
              component_checkout="$repository_root/$component_local_path"
              printf '\n%s\n' "$component_input"
              printf '  remote input: %s\n' "''${component_remotes[$index]}"
              printf '  local path:   ./%s\n' "$component_local_path"
              if [[ -f "$component_checkout/flake.nix" ]]; then
                printf '  status:       active\n'
              else
                printf '  status:       unavailable (checkout not initialized)\n'
              fi
            done
                    }

                    case "$operation" in
                      overrides)
                        print_overrides
                        ;;
                      locked-metadata)
                        printf '%s\n' "Locked public component revisions:"
                        jq -r '.nodes | to_entries[] | select(.key|IN("arbor-manager","arbor-registry","arbor-network-manager","yggdrasil-private")) | "  \(.key)=\(.value.locked.rev)"' flake.lock
                        ;;
                      develop|check|show|metadata|build|eval)
                        collect_overrides
                        case "$operation" in
                          develop)  exec nix develop "''${overrides[@]}" "$@" ;;
                          check)    exec nix flake check "''${overrides[@]}" "$@" ;;
                          show)     exec nix flake show "''${overrides[@]}" "$@" ;;
                          metadata) exec nix flake metadata "''${overrides[@]}" "$@" ;;
                          build)    exec nix build "''${overrides[@]}" "$@" ;;
                          eval)     exec nix eval "''${overrides[@]}" "$@" ;;
                        esac
                        ;;
                      *)
                        cat >&2 <<'EOF'
          Usage: nix-arbor-local <operation> [nix arguments...]

          Operations:
            develop    Enter the devshell with available local component overrides
            check      Run flake checks with available local component overrides
            show       Show flake outputs with available local component overrides
            metadata   Show flake metadata with available local component overrides
            locked-metadata  Print the committed public component revisions (no overrides)
            build      Build an installable with available local component overrides
            eval       Evaluate an installable with available local component overrides
            overrides  Show which local component overrides are active
          EOF
                        exit 2
                        ;;
                    esac
        '';
      };
    in
    {
      packages.navi-help = help;
      packages.local = local;

      apps.help = {
        type = "app";
        program = "${help}/bin/nix-arbor-help";
        meta.description = "Browse Nix Arbor's project-local Navi cheats";
      };

      apps.local = {
        type = "app";
        program = "${local}/bin/nix-arbor-local";
        meta.description = "Run Nix commands with available local component overrides";
      };
    };
}
