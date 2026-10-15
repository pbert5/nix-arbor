{
  inputs,
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
        nix-binary-cache-config =
          let
            cacheSystem = inputs.nixpkgs.lib.nixosSystem {
              system = pkgs.stdenv.hostPlatform.system;
              modules = [
                config.flake.nixosModules.arbor-nix-binary-cache
                (_: {
                  arbor.nixBinaryCache = {
                    enable = true;
                    endpoint = "https://cache.example.invalid/";
                    allowedHosts = [ "cache.example.invalid" ];
                  };
                })
              ];
            };
            cache = cacheSystem.config;
            storageSetup = cache.systemd.services.arbor-nix-binary-cache-storage.script;
            atticService = cache.systemd.services.atticd;
          in
          assert
            cache.services.atticd.settings.database.url
            == "sqlite:////mypool/nix-binary-cache/database/server.db?mode=rwc";
          assert cache.services.atticd.settings.storage.path == "/mypool/nix-binary-cache/storage";
          assert atticService.serviceConfig.User == "atticd";
          assert cache.services.atticd.environmentFile == "/run/secrets/attic-server.env";
          assert
            builtins.match ".*mountpoint -q /mypool.*install -d -o root -g root -m 0711 /mypool/nix-binary-cache.*install -d -o atticd -g atticd -m 0700 /mypool/nix-binary-cache/database.*install -d -o atticd -g atticd -m 0700 /mypool/nix-binary-cache/storage.*" storageSetup
            != null;
          assert builtins.match ".*mountpoint -q /mypool.*" atticService.serviceConfig.ExecStartPre != null;
          assert !(lib.hasPrefix "/nix/store/" cache.services.atticd.environmentFile);
          pkgs.runCommand "nix-arbor-nix-binary-cache-config" { } ''
            touch $out
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
