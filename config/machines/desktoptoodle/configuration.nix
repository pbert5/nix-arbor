{ config, lib, ... }:
{
  imports = [
    ./gaming-bitlocker.nix
    ./graphics.nix
    ./peripherals.nix
  ];

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

  # This is the existing, narrowly scoped machine recovery grant.  It is
  # public-key-only; no private key or root password is declared here.
  users.users.root.openssh.authorizedKeys.keys = (import ../../access).r640EvolverDeployerKeys;

  arbor.desktoptoodle.gamingBitlocker = {
    enable = true;
    device = "/dev/disk/by-uuid/657ff291-de57-40c0-80d9-9362895587e8";
    keyFiles = [
      "/etc/nix-arbor/secrets/desktoptoodle/bitlocker/E07B243F.recovery"
      "/etc/nix-arbor/secrets/desktoptoodle/bitlocker/0EE6F93C.recovery"
    ];
  };
}
