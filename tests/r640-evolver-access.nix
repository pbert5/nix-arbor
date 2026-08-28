{ lib }:
let
  evaluated = lib.evalModules {
    modules = [
      (import ../config/env.nix)
      (import ../config/machines/r640-0/access.nix)
    ];
  };
  host = evaluated.config.arbor.environment.public.sshHosts.eVolver;
in
assert host.hostname == "200:c739:8dc3:8e5a:b1b4:bf7b:1142:d29a";
assert host.user == "root";
assert host.identityFile == [ "/home/ash/.ssh/cluster-leader-ed25519" ];
assert host.extraOptions.IdentitiesOnly == "yes";
true
