{
  config,
  inputs,
  lib,
  ...
}:
let
  eVolver = config.flake.nixosConfigurations.eVolver.config;
  packageNames = map (
    package: package.pname or package.name or ""
  ) eVolver.environment.systemPackages;
  requiredPackageNames = [
    "codex"
    "codex-switch"
    "docker-compose"
    "devcontainer"
    "gh"
    "git"
    "nodejs"
    "rtk"
    "uv"
  ];
in
{
  perSystem =
    { pkgs, system, ... }:
    let
      src = ../.;
    in
    {
      checks = {
        free-rtk = import ./rtk-check.nix {
          inherit
            config
            inputs
            pkgs
            system
            ;
        };
        host-security = import ./security-check.nix { inherit config lib pkgs; };
        raspberry-evolver =
          pkgs.runCommand "nix-arbor-raspberry-evolver-tests"
            {
              nativeBuildInputs = with pkgs; [
                python3
                e2fsprogs
                util-linux
                zstd
                git
                nix
                jq
                ripgrep
              ];
            }
            ''
              cp -r ${src} source
              chmod -R u+w source
              patchShebangs source/tools/raspberry-evolver
              substituteInPlace source/tests/raspberry-evolver-tools/test_{doctor,help}.py \
                --replace-fail /run/current-system/sw/bin/bash ${pkgs.bash}/bin/bash
              cd source
              export PYTHONDONTWRITEBYTECODE=1
              python3 -m unittest discover -s tests/raspberry-evolver-tools
              touch "$out"
            '';
        evolver-developer-tools =
          assert lib.all (name: lib.elem name packageNames) requiredPackageNames;
          assert eVolver.virtualisation.docker.enable;
          pkgs.runCommand "nix-arbor-evolver-developer-tools" { } ''
            touch $out
          '';

        nixfmt = pkgs.runCommand "nix-arbor-nixfmt" { } ''
          { find ${src}/config ${src}/modules -type f -name '*.nix' -print0; printf '%s\\0' ${src}/flake.nix; } \
            | xargs -0 ${pkgs.nixfmt}/bin/nixfmt --check
          touch $out
        '';

        statix = pkgs.runCommand "nix-arbor-statix" { } ''
          ${pkgs.statix}/bin/statix check ${../modules}
          touch $out
        '';

        deadnix = pkgs.runCommand "nix-arbor-deadnix" { } ''
          ${pkgs.deadnix}/bin/deadnix --fail ${../flake.nix} ${../modules}
          touch $out
        '';
      };
    };
}
