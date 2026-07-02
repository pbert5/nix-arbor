{
  hostInventory,
  lib,
  ...
}:
let
  cfg = lib.attrByPath [ "org" "network" "directLink" ] null hostInventory;
  enabled = cfg != null;
  profileName = if enabled then "direct-link-${cfg.peer}" else "direct-link";
in
{
  assertions = lib.optionals enabled [
    {
      assertion = cfg ? interfaceName && cfg ? address && cfg ? peer && cfg ? peerAddress;
      message = ''
        network/direct-link requires org.network.directLink.interfaceName,
        address, peer, and peerAddress.
      '';
    }
  ];

  networking.networkmanager.ensureProfiles.profiles = lib.mkIf enabled {
    ${profileName} = {
      connection = {
        id = profileName;
        type = "ethernet";
        interface-name = cfg.interfaceName;
        autoconnect = true;
        autoconnect-priority = 200;
      };
      ipv4 = {
        method = "manual";
        addresses = cfg.address;
        never-default = true;
      };
      ipv6.method = "disabled";
    };
  };

  programs.ssh.extraConfig = lib.optionalString enabled ''
    Host ${cfg.peer}-direct
      HostName ${cfg.peerAddress}
      HostKeyAlias ${cfg.peer}
  '';
}
