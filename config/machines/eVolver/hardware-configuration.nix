{
  config,
  lib,
  modulesPath,
  ...
}:
{
  imports = [ (modulesPath + "/installer/scan/not-detected.nix") ];

  boot.initrd.availableKernelModules = [
    "xhci_pci"
    "ahci"
    "nvme"
    "usb_storage"
    "usbhid"
    "sd_mod"
  ];
  boot.kernelModules = [ "kvm-intel" ];

  # The generated 2026-07-17 capture used filesystem labels.  They remain
  # stable across the supported installation layout and avoid a guessed UUID.
  fileSystems."/" = {
    device = "/dev/disk/by-label/nixos-root";
    fsType = "ext4";
  };
  fileSystems."/boot" = {
    device = "/dev/disk/by-label/NIXBOOT";
    fsType = "vfat";
    options = [
      "fmask=0077"
      "dmask=0077"
    ];
  };
  # The host has 7.5 GiB RAM and ample ext4 capacity.  Keep an 8 GiB
  # disk-backed emergency tier available behind zram; this is not hibernation
  # storage and hibernation remains disabled in the machine configuration.
  swapDevices = [
    {
      # nixpkgs 26.11 requires a label field in this submodule; force the
      # file path so the label helper does not reinterpret it as a block path.
      device = lib.mkForce "/var/lib/swapfile";
      label = "evolver-swap";
      size = 8192;
    }
  ];

  nixpkgs.hostPlatform = lib.mkDefault "x86_64-linux";
  hardware.cpu.intel.updateMicrocode = lib.mkDefault config.hardware.enableRedistributableFirmware;
}
