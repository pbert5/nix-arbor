{ lib, site, ... }:
let
  gameLibrary = site.storage.gameLibrary;
  exportHosts = gameLibrary.export.hosts or [ ];
  exportOptions = gameLibrary.export.options or [ ];
  yggIfName = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "defaults"
    "ifName"
  ] "ygg0" site;
  mkExport = host: "${host}(${lib.concatStringsSep "," exportOptions})";
in
{
  services.nfs.server = {
    enable = true;
    exports = ''
      ${gameLibrary.localPath} ${lib.concatStringsSep " " (builtins.map mkExport exportHosts)}
    '';
  };

  # NFSv4 uses TCP/2049. Keep the game library reachable only through the
  # private Yggdrasil overlay used by the export allowlist and client source.
  networking.firewall.interfaces.${yggIfName}.allowedTCPPorts = [ 2049 ];
}
