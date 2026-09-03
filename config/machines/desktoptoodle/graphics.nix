{ config, pkgs, ... }:
{
  # desktoptoodle has an RTX 2060 SUPER; host evidence identifies kernel
  # 6.18.37 and NVIDIA 580.142, so retain their compatible package lines.
  boot.kernelPackages = pkgs.linuxPackages_6_18;
  boot.blacklistedKernelModules = [ "nouveau" ];

  services.xserver.videoDrivers = [ "nvidia" ];

  hardware.nvidia = {
    modesetting.enable = true;
    open = false;
    package = config.boot.kernelPackages.nvidiaPackages.legacy_580;
  };
}
