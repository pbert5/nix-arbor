{ lib, site, hostInventory, hostName, ... }:
let
  fabric = site.storageFabric or { };
  radicleOrg = lib.attrByPath [ "org" "network" "radicle" ] { } hostInventory;
  # Radicle node binds to the private Ygg address only.
  yggAddress = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "nodes"
    hostName
    "address"
  ] null site;
  bindAddr = if yggAddress != null then yggAddress else "127.0.0.1";
  nodePort = radicleOrg.port or (lib.attrByPath [ "ports" "radicleNode" "port" ] 8776 site);
in
{
  assertions = [
    {
      assertion = yggAddress != null;
      message = ''
        Host "${hostName}" includes the network/radicle dendrite but has no
        privateYggdrasil address.  Radicle must bind to the private overlay.
        Enroll the host in inventory.networks.privateYggdrasil.nodes.
      '';
    }
  ];

  environment.etc."radicle/config.json".text = builtins.toJSON {
    node = {
      listen = [ "${bindAddr}:${toString nodePort}" ];
      # Announce only to private overlay peers.
      externalAddresses = lib.optionals (yggAddress != null) [
        "${yggAddress}:${toString nodePort}"
      ];
    };
  };
}
