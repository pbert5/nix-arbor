{ pkgs, lib, ... }:
{
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
  services.journald.extraConfig = ''
    Storage=persistent
    SystemMaxUse=64M
    RuntimeMaxUse=32M
    MaxRetentionSec=1month
  '';
  boot.tmp.cleanOnBoot = true;
  systemd.services.raspberry-evolver-maintenance = {
    description = "Collect old Raspberry Pi system generations";
    path = with pkgs; [
      coreutils
      util-linux
      gawk
      nix
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${pkgs.bash}/bin/bash ${./maintenance.sh}";
    };
  };
  systemd.timers.raspberry-evolver-maintenance = {
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "weekly";
      Persistent = true;
    };
  };
  systemd.services.raspberry-evolver-bootstrap = {
    description = "Enroll raspberry-evolver when its bootstrap key is available";
    after = [ "tailscaled.service" ];
    wants = [ "tailscaled.service" ];
    path = with pkgs; [
      coreutils
      jq
      tailscale
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${pkgs.bash}/bin/bash ${./bootstrap.sh}";
      TimeoutStartSec = 120;
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
