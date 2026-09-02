{ config, lib, ... }:
{
  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 20;
  boot.loader.efi.canTouchEfiVariables = lib.mkDefault true;

  assertions = [
    {
      assertion = lib.elem "r640EvolverDeployer" config.arbor.access.authorizedKeySets;
      message = "desktoptoodle must opt into the explicit r640 public SSH grant";
    }
    {
      assertion = lib.any (
        key:
        lib.hasPrefix "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINa/sAnukQD4gdu8zZ/m3+SavLJNrtjJcC4swgebGnZN" key
      ) config.users.users.ash.openssh.authorizedKeys.keys;
      message = "desktoptoodle must authorize the r640 machine public SSH key for Ash";
    }
  ];
}
