{ lib, site, ... }:
let
  gameLibrary = site.storage.gameLibrary;
  exportHosts = gameLibrary.export.hosts or [ ];
  exportOptions = gameLibrary.export.options or [ ];
  mkExport = host: "${host}(${lib.concatStringsSep "," exportOptions})";
in
{
  services.nfs.server = {
    enable = true;
    exports = ''
      ${gameLibrary.localPath} ${lib.concatStringsSep " " (builtins.map mkExport exportHosts)}
    '';
  };
}
