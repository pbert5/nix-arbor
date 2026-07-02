# Hardware configuration for t320-0 (Dell PowerEdge T320)
# Intel Xeon E5-2470 v2, 94GB RAM, LSI MegaRAID SAS 2008 in JBOD mode
#
# NOTE: This file is used directly by the bootstrap live installer.
# The NixOS root disk is the dedicated 185.8G SSD presented as /dev/sdf.
# Large data drives and the 1TB `fast` SSD pool are preserved in place.
#
# Disk layout on sdf (PERC H310-presented 185.8G SSD - NixOS boot/root):
#   sdf1  1G     EFI System Partition   label NIXBOOT
#   sdf2  rest   NixOS root ext4        label nixos-root
#
# Preserved data pools (not touched by install):
#   small single  sdb        (ST3000DM008 3TB)
#   fast  single  sdc        (Crucial MX500 1TB SSD)
#   big   mirror  sdd + sde  (12TB + 12TB)
{
  config,
  lib,
  pkgs,
  modulesPath,
  hostInventory,
  ...
}:

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

  # Preserve the existing label-based mounts while bare-metal installation is
  # disabled. Disko owns these mounts only during an explicitly enabled install.
  fileSystems = lib.mkIf (!(lib.attrByPath [ "org" "install" "enable" ] false hostInventory)) {
    "/" = {
      device = "/dev/disk/by-label/nixos-root";
      fsType = "ext4";
    };

    "/boot" = {
      device = "/dev/disk/by-label/NIXBOOT";
      fsType = "vfat";
      options = [
        "fmask=0077"
        "dmask=0077"
      ];
    };
  };

  swapDevices = [ ];

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  hardware.cpu.intel.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;
}
