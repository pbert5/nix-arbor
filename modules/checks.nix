{
  config,
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
    { pkgs, ... }:
    let
      src = ../.;
    in
    {
      checks = {
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
