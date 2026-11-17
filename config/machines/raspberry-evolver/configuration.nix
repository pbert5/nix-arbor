{ pkgs, ... }:
{
  # The Pi bootloader installs firmware DTBs; the upstream kernel package lacks
  # the buildDTBs attribute expected by the root nixpkgs device-tree default.
  hardware.deviceTree.enable = false;
  system.boot.loader.kernelFile = "Image";
  system.stateVersion = "26.05";
  nix.settings.experimental-features = [
    "nix-command"
    "flakes"
  ];
  networking.networkmanager.enable = true;
  services.tailscale.enable = true;
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "no";
    };
  };
  users.users.ash = {
    uid = 1000;
    isNormalUser = true;
    extraGroups = [
      "wheel"
      "networkmanager"
    ];
    openssh.authorizedKeys.keys = (import ../../access).operatorKeys;
  };
  security.sudo.wheelNeedsPassword = false;
  zramSwap = {
    enable = true;
    memoryPercent = 25;
  };
  services.journald.settings.Journal = {
    Storage = "persistent";
    SystemMaxUse = "64M";
    RuntimeMaxUse = "32M";
    MaxRetentionSec = "1month";
  };
  boot.tmp.cleanOnBoot = true;
  nix.gc = {
    automatic = true;
    dates = "weekly";
    options = "--delete-older-than 14d";
  };
  systemd.services.raspberry-evolver-bootstrap = {
    description = "Enroll raspberry-evolver when its bootstrap key is available";
    after = [ "tailscaled.service" ];
    wants = [ "tailscaled.service" ];
    path = with pkgs; [
      coreutils
      jq
      tailscale
      util-linux
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${pkgs.bash}/bin/bash ${./bootstrap.sh}";
      TimeoutStartSec = 600;
      UMask = "0077";
    };
  };
  systemd.timers.raspberry-evolver-bootstrap = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "30s";
      OnUnitInactiveSec = "2min";
    };
  };
}
