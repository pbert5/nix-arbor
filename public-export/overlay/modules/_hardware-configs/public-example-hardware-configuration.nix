{ ... }:
{
  boot.loader.grub.devices = [ "/dev/sda" ];

  fileSystems."/" = {
    device = "/dev/disk/by-uuid/REDACTED-UUID";
    fsType = "ext4";
  };
}
