{ config, lib, ... }:
let
  access = import ../../access;
in
{
  imports = [ ../../access/module.nix ];

  networking.hostName = "canoodle";
  networking.networkmanager.enable = true;

  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 20;
  boot.loader.efi.canTouchEfiVariables = lib.mkDefault true;

  # The preserved hardware record identifies a hybrid Intel/NVIDIA laptop.
  # Keep the driver setup required for its known display hardware without
  # importing legacy desktop-session policy or application configuration.
  services.xserver.videoDrivers = [ "nvidia" ];
  hardware.nvidia = {
    modesetting.enable = true;
    open = false;
    prime = {
      intelBusId = "PCI:0:2:0";
      nvidiaBusId = "PCI:1:0:0";
      offload.enable = true;
      offload.enableOffloadCmd = true;
    };
  };

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };
  arbor.access.authorizedKeySets = [
    "operator"
    "deployment"
  ];
  users.users.ash.openssh.authorizedKeys.keys = lib.concatMap (
    set: access."${set}Keys"
  ) config.arbor.access.authorizedKeySets;
}
