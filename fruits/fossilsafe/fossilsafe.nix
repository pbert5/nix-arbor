{ lib, storageTape ? null, ... }:
{
  imports = [ ./nix/fossilsafe-module.nix ];

  config = lib.mkIf (storageTape != null && storageTape.selectedLtfsManager == "fossilsafe") {
    services.fossilsafe = {
      bootstrap = storageTape.fossilsafe.bootstrap;
      enable = true;
      openFirewall = storageTape.fossilsafe.openFirewall;
      package = storageTape.fossilsafe.package;
      requireApiKey = storageTape.fossilsafe.requireApiKey;
      settings = lib.recursiveUpdate
        {
          allowed_origins = builtins.map
            (host: "http://${host}:${toString storageTape.fossilsafe.endpoint.port}")
            storageTape.fossilsafe.endpoint.hosts;
          backend_bind = storageTape.fossilsafe.endpoint.bind;
          backend_port = storageTape.fossilsafe.endpoint.port;
        }
        storageTape.fossilsafe.settings;
      skipHardwareInit = storageTape.fossilsafe.skipHardwareInit;
      stateDir = storageTape.fossilsafe.stateDir;
    };
  };
}
