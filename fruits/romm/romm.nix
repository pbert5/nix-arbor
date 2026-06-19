{
  hostInventory,
  lib,
  site,
  ...
}:
let
  rommOrg = lib.attrByPath [ "org" "romm" ] { } hostInventory;
  endpoint = site.ports.romm;
in
{
  imports = [ ./nix/romm-module.nix ];

  services.romm = {
    enable = true;
    inherit endpoint;
    scanWorkers = rommOrg.scanWorkers or 1;
    libraryDir = rommOrg.libraryDir or "/fast/GameLibrary";
    stateDir = rommOrg.stateDir or "/var/lib/romm";
    providerEnvironmentFile = rommOrg.providerEnvironmentFile or "/var/lib/romm/secrets/providers.env";
  };
}
