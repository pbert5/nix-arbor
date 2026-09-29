{ lib }:
let
  evaluated = lib.evalModules {
    modules = [
      (import ../config/env.nix)
      (
        { config, ... }:
        {
          arbor.environment.public.sshHosts.desktoptoodle = {
            hostname = "desktoptoodle";
            identityFile = [ config.arbor.environment.externalFiles.files.desktoptoodleSshIdentity.path ];
          };
        }
      )
    ];
  };
  config = evaluated.config;
  files = config.arbor.environment.externalFiles.files;
in
assert config.arbor.environment.externalFiles.root == "/etc/nix-arbor";
assert files.r640SopsFile.path == "/etc/nix-arbor/r640-0.sops.yaml";
assert files.ashPasswordHash.neededForUsers;
assert files.ashPasswordHash.owner == "root";
assert files.ashPasswordHash.group == "root";
assert files.ashPasswordHash.mode == "0400";
assert files.desktoptoodleSshIdentity.owner == "ash";
assert files.desktoptoodleSshIdentity.mode == "0400";
assert
  config.arbor.environment.public.sshHosts.desktoptoodle.identityFile == [
    "/home/ash/.ssh/desktoptoodle"
  ];
true
