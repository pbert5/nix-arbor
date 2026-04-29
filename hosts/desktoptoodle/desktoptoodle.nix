{ config, lib, pkgs, ... }:
{
  imports = [ ./ash-desktop.nix ];

  networking.hostName = "desktoptoodle";

  boot.loader.grub.enable = lib.mkForce false;
  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 30;
  boot.loader.efi.canTouchEfiVariables = true;
  boot.tmp.useTmpfs = false;
  boot.blacklistedKernelModules = [ "nouveau" ];
  boot.kernelModules = [ "uvcvideo" ];

  systemd.services.NetworkManager-wait-online.enable = lib.mkForce false;

  services.xserver.videoDrivers = [ "nvidia" ];

  hardware.nvidia = {
    modesetting.enable = true;
    nvidiaSettings = true;
    open = false;
    package = config.boot.kernelPackages.nvidiaPackages.stable;
  };

  users.users.ash.extraGroups = [
    "audio"
    "home-share"
    "tape"
    "video"
  ];

  environment.systemPackages = with pkgs; [
    alsa-utils
    libcamera
    pulseaudio
    usbutils
    v4l-utils
  ];

  systemd.tmpfiles.rules = [
    "L+ /home/example/games - - - - /srv/games"
  ];
}
