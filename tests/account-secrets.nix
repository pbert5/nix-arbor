{ lib }:
let
  external = lib.evalModules {
    modules = [
      (import ../config/env.nix)
      {
        arbor.environment.secrets = {
          enable = true;
          provider = "external-files";
        };
      }
    ];
  };
  defaults = lib.evalModules { modules = [ (import ../config/env.nix) ]; };
in
assert external.config.arbor.environment.secrets.provider == "external-files";
assert
  external.config.arbor.environment.externalFiles.files.ashPasswordHash.path
  == "/run/secrets/ash-password";
assert external.config.arbor.environment.externalFiles.files.ashPasswordHash.neededForUsers;
assert defaults.config.arbor.environment.secrets.provider == "sops";
true
