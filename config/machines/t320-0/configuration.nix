{ ... }:
{
  imports = [
    ../../access/module.nix
    ../../users
  ];

  arbor.access.authorizedKeySets = [
    "operator"
    "deployment"
  ];

  boot.loader.systemd-boot = {
    enable = true;
    configurationLimit = 10;
  };
  # Firmware NVRAM contains legacy entries. The EFI fallback path is already
  # used by this host, so deployment must not add or alter NVRAM boot entries.
  boot.loader.efi.canTouchEfiVariables = false;
  services.lvm.enable = false;

  networking.networkmanager = {
    enable = true;
    ensureProfiles.profiles = {
      lan-bridge = {
        connection = {
          id = "lan-bridge";
          type = "bridge";
          interface-name = "br0";
          autoconnect = true;
          autoconnect-priority = 200;
        };
        bridge.stp = false;
        ipv4.method = "auto";
        ipv6.method = "auto";
      };
      lan-bridge-eno1 = {
        connection = {
          id = "lan-bridge-eno1";
          type = "ethernet";
          interface-name = "eno1";
          controller = "br0";
          port-type = "bridge";
          autoconnect = true;
        };
        ipv4.method = "disabled";
        ipv6.method = "disabled";
      };
      lan-bridge-eno2 = {
        connection = {
          id = "lan-bridge-eno2";
          type = "ethernet";
          interface-name = "eno2";
          controller = "br0";
          port-type = "bridge";
          autoconnect = true;
        };
        ipv4.method = "disabled";
        ipv6.method = "disabled";
      };
    };
  };
  systemd.services.NetworkManager-wait-online.enable = false;
}
