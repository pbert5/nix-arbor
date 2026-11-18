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
        existing-root-pair =
          let
            registry = inputs.arbor-registry;
            runtime = pkgs.callPackage (registry + "/runtime/package.nix") { };
            transport = pkgs.callPackage (registry + "/transport/package.nix") { };
            hosts = map (name: config.flake.nixosConfigurations.${name}.config) [
              "r640-0"
              "eVolver"
            ];
            matches =
              host:
              host.cluster.registry.runtime.enable
              && host.cluster.registry.runtime.runtimePackage.drvPath == runtime.drvPath
              && host.cluster.registry.runtime.transportPackage.drvPath == transport.drvPath
              && lib.any (package: package.drvPath == runtime.drvPath) host.environment.systemPackages;
          in
          assert system != "x86_64-linux" || lib.all matches hosts;
          import (registry + "/tests/existing-root-pair.nix") { inherit pkgs runtime transport; };
        registry-lifecycle =
          pkgs.runCommand "nix-arbor-registry-lifecycle"
            {
              nativeBuildInputs = [
                pkgs.bash
                pkgs.coreutils
                pkgs.gnugrep
                pkgs.gnused
                pkgs.jq
              ];
            }
            (
              builtins.concatStringsSep "\n" [
                "mkdir -p work/tests/arbor-registry work/tools/arbor"
                "cp ${src}/tests/arbor-registry/lifecycle.sh work/tests/arbor-registry/"
                "cp ${src}/tools/arbor/registry ${src}/tools/arbor/registry-host.sh work/tools/arbor/"
                "chmod u+w work/tools/arbor/registry"
                "sed -i '1c#!${pkgs.bash}/bin/bash' work/tools/arbor/registry"
                "bash work/tests/arbor-registry/lifecycle.sh"
                "touch $out"
              ]
            );
        fastfetch-status =
          pkgs.runCommand "nix-arbor-fastfetch-status"
            {
              nativeBuildInputs = [
                pkgs.bash
                pkgs.coreutils
                pkgs.jq
              ];
            }
            ''
              cd ${src}
              bash tests/fastfetch-status.sh
              touch $out
            '';
        free-rtk = import ./rtk-check.nix {
          inherit
            config
            inputs
            pkgs
            system
            ;
        };
        host-security = import ./security-check.nix { inherit config lib pkgs; };
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
