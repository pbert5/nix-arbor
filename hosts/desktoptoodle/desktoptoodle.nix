{ config, lib, pkgs, ... }:
let
  disabledTapeServices = [
    "fossilsafe"
    "tapelib-cache-cleanup"
    "tapelib-db-backup"
    "tapelib-fuse"
    "tapelib-games-backup-run-next"
    "tapelib-inventory"
    "tapelib-verify"
    "tapelib-web"
    "tapelibd"
  ];
  disabledTapeTimers = [
    "tapelib-cache-cleanup"
    "tapelib-db-backup"
    "tapelib-inventory"
    "tapelib-verify"
  ];
  steamBitlockerCompatData = "/home/example/.local/share/Steam/steamapps/compatdata-piss-boi";
  steamBitlockerLibraryCompatData = "/mnt/bitlocker/piss_boi/games/steamapps/compatdata";
  steamBitlockerCompatMountUnit = "mnt-bitlocker-piss_boi-games-steamapps-compatdata.mount";
in
{
  imports = [ ./ash-desktop.nix ];

  networking.hostName = "desktoptoodle";

  boot.loader.grub.enable = lib.mkForce false;
  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 30;
  boot.loader.efi.canTouchEfiVariables = true;
  boot.tmp.useTmpfs = false;
  # Temporary CopyFail mitigation: the updated nixpkgs lock still resolves the
  # default desktoptoodle kernel to 6.12.84, so force a fixed kernel line here
  # and block the vulnerable algif_aead module from loading.
  boot.kernelPackages = pkgs.linuxPackages_latest;
  boot.blacklistedKernelModules = [
    "nouveau"
    "algif_aead"
  ];
  boot.extraModprobeConfig = ''
    install algif_aead /run/current-system/sw/bin/false
    blacklist algif_aead
  '';
  boot.kernelModules = [ "uvcvideo" ];

  systemd.services =
    {
      NetworkManager-wait-online.enable = lib.mkForce false;
      networkmanager-disable-broken-eno1-autoconnect = {
        description = "Disable desktoptoodle's broken eno1 autoconnect profile";
        after = [ "NetworkManager.service" ];
        wants = [ "NetworkManager.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "oneshot";
        };
        script = ''
          if ${pkgs.networkmanager}/bin/nmcli connection show "Wired connection 1" >/dev/null 2>&1; then
            ${pkgs.networkmanager}/bin/nmcli connection modify "Wired connection 1" connection.autoconnect no
            ${pkgs.networkmanager}/bin/nmcli connection down "Wired connection 1" >/dev/null 2>&1 || true
          fi
        '';
      };
      steam-bitlocker-compatdata-target = {
        description = "Prepare native Proton compatdata for the piss_boi Steam library";
        requires = [ "bitlocker-mount-pissBoi.service" ];
        after = [
          "bitlocker-mount-pissBoi.service"
          "systemd-tmpfiles-setup.service"
        ];
        before = [ steamBitlockerCompatMountUnit ];
        wantedBy = [ "multi-user.target" ];
        path = [ pkgs.coreutils ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          install -d -o ash -g users -m 0755 ${lib.escapeShellArg steamBitlockerCompatData}
          install -d -o ash -g users -m 0755 ${lib.escapeShellArg steamBitlockerLibraryCompatData}
        '';
      };
    }
    // lib.genAttrs disabledTapeServices (_: {
      enable = lib.mkForce false;
      wantedBy = lib.mkForce [ ];
    });

  systemd.mounts = [
    {
      description = "Native Proton compatdata for the piss_boi Steam library";
      what = steamBitlockerCompatData;
      where = steamBitlockerLibraryCompatData;
      type = "none";
      options = "bind";
      requires = [
        "bitlocker-mount-pissBoi.service"
        "steam-bitlocker-compatdata-target.service"
      ];
      after = [
        "bitlocker-mount-pissBoi.service"
        "steam-bitlocker-compatdata-target.service"
      ];
      wantedBy = [ "multi-user.target" ];
    }
  ];

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
    "L+ /home/example/piss_boi - - - - /mnt/bitlocker/piss_boi"
    "d ${steamBitlockerCompatData} 0755 ash users - -"
  ];

  systemd.timers = lib.genAttrs disabledTapeTimers (_: {
    enable = lib.mkForce false;
    wantedBy = lib.mkForce [ ];
  });
}
