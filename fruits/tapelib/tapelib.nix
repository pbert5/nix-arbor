{
  lib,
  storageTape ? null,
  ...
}:
{
  imports = [ ./nix/tapelib-module.nix ];

  config = lib.mkIf (storageTape != null && storageTape.selectedLtfsManager == "tapelib") {
    services.tapelib = {
      enable = true;
      inherit (storageTape.tapelib) openFirewall package stateDir;
      library = storageTape.tapelib.library;
      cache = storageTape.tapelib.cache;
      fuse = storageTape.tapelib.fuse;
      database = storageTape.tapelib.database;
      games = storageTape.tapelib.games;
      webui = storageTape.tapelib.webui;
    };
  };
}
