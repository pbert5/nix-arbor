# Hardware configuration for t320-truenas-scale (Dell PowerEdge T320)
# Intel Xeon E5-2470 v2, 94GB RAM, LSI MegaRAID SAS 2008 in JBOD mode
#
# NOTE: This file was hand-authored from hardware gathered via SSH while the
# machine still runs TrueNAS Scale. The root filesystem UUID is a placeholder.
# After running `nixos-install`, replace the root UUID with the real one from
# `blkid /dev/sde3`, or regenerate this file with `nixos-generate-config`.
#
# Disk layout on sde (Crucial CT480M500SSD1, 447GB - boot drive):
#   sde1  1M     BIOS boot
#   sde2  512M   EFI (UUID: 1EF1-6111)  <-- preserved from TrueNAS
#   sde3  446.6G NixOS root ext4        <-- reformatted during NixOS install
#
# ZFS data pools (on separate drives, imported by NixOS after boot):
#   big   mirror  sdb + sdd  (2x Seagate Exos 10.9TB)   /mnt/big
#   fast  single  sdc        (Crucial MX500 1TB SSD)     /mnt/fast
{ config, lib, pkgs, modulesPath, ... }:

{
  imports = [
    (modulesPath + "/installer/scan/not-detected.nix")
  ];

  # Drives attach via LSI MegaRAID SAS 2008 (in JBOD/passthrough mode) and
  # the onboard Intel AHCI controller.
  boot.initrd.availableKernelModules = [
    "ahci"
    "xhci_pci"
    "megaraid_sas"
    "usb_storage"
    "usbhid"
    "sd_mod"
  ];
  boot.initrd.kernelModules = [ ];
  boot.kernelModules = [ "kvm-intel" ];
  boot.extraModulePackages = [ ];

  # TODO: replace UUID with output of `blkid /dev/sde3` after NixOS install
  fileSystems."/" = {
    device = "/dev/disk/by-uuid/REDACTED-UUID";
    fsType = "ext4";
  };

  fileSystems."/boot" = {
    device = "/dev/disk/by-uuid/1EF1-6111";
    fsType = "vfat";
    options = [ "fmask=0077" "dmask=0077" ];
  };

  swapDevices = [ ];

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  hardware.cpu.intel.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;
}
