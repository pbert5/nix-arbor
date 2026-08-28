{ inputs, ... }:
{
  perSystem =
    { pkgs, system, ... }:
    let
      ashzshHome = inputs.home-manager.lib.homeManagerConfiguration {
        inherit pkgs;
        modules = [
          inputs.ashzsh.homeModules.default
          {
            home = {
              username = "ash";
              homeDirectory = "/tmp/nix-arbor-ashzsh";
              stateVersion = "26.05";
              enableNixpkgsReleaseCheck = false;
            };
            systemd.user.startServices = "suggest";
          }
        ];
      };
    in
    {
      formatter = pkgs.nixfmt-tree;

      packages.codex-switch = inputs.codex-switch.packages.${system}.codex-switch;

      devShells.default = pkgs.mkShell {
        name = "nix-arbor";
        packages = (inputs.ashes-tools.lib.sets.nix-workstation pkgs) ++ [
          pkgs.codex
          pkgs.rtk
          pkgs.nodejs
          pkgs.playwright-mcp
          inputs.codex-switch.packages.${system}.codex-switch
        ];

        shellHook = ''
          export HOME="/tmp/nix-arbor-ashzsh"
          export SHELL="${pkgs.zsh}/bin/zsh"
          mkdir -p "$HOME"
          ashzsh_marker="$HOME/.ashzsh-activation"
          if [[ ! -r "$ashzsh_marker" || "$(<"$ashzsh_marker")" != "${ashzshHome.activationPackage}" ]]; then
            ${ashzshHome.activationPackage}/activate
            printf '%s\n' "${ashzshHome.activationPackage}" > "$ashzsh_marker"
          fi
          if [[ -r "$HOME/.nix-profile/etc/profile.d/hm-session-vars.sh" ]]; then
            source "$HOME/.nix-profile/etc/profile.d/hm-session-vars.sh"
          fi
          export NAVI_PATH="$PWD/cheats''${NAVI_PATH:+:$NAVI_PATH}"
          if [[ -z "''${NIX_ARBOR_WELCOME_SHOWN:-}" ]]; then
            export NIX_ARBOR_WELCOME_SHOWN=1
            printf '%s\n' \
              "Nix Arbor shell: nix flake show | nix flake check | nix fmt" \
              "Navi cheats: navi (project cheats are first in NAVI_PATH)"
          fi
          if [[ $- == *i* ]]; then
            exec "${pkgs.zsh}/bin/zsh" -i
          fi
        '';
      };
    };
}
