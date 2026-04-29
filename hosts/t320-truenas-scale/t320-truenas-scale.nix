{ lib, ... }:
{
  networking.hostName = "t320-truenas-scale";

  # EFI boot — sde2 is the existing EFI partition from the TrueNAS install,
  # sde3 will hold the NixOS root after installation.
  boot.loader.grub.enable = lib.mkForce false;
  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 10;
  boot.loader.efi.canTouchEfiVariables = true;

  # Import the `fast` SSD pool in addition to `big` (handled by storage/zfs dendrite).
  # Both pools mount under /mnt by default (as TrueNAS set them up).
  boot.zfs.extraPools = [ "fast" ];

  users.users.ash.uid = 1000;
  users.users.ash.linger = true;
}
