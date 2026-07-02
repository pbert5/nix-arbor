{
  config,
  lib,
  pkgs,
  ...
}:
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
  vmHyprlandSession = {
    command = "${lib.getExe pkgs.uwsm} start hyprland.desktop";
    user = "ash";
  };
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

  systemd.services = {
    NetworkManager-wait-online.enable = lib.mkForce false;
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

  # Blue Microphone (USB) has auto-profile disabled; pin it to iec958-stereo
  # which is how ALSA names the USB audio class capture on this device.
  # The analog-stereo profile uses front:0 which cannot open the capture PCM.
  services.pipewire.wireplumber.extraConfig = {
    "10-blue-microphone-profile" = {
      "monitor.alsa.rules" = [
        {
          matches = [ { "device.name" = "~alsa_card.usb-Generic_Blue_Microphones.*"; } ];
          actions.update-props."device.profile" = "output:iec958-stereo+input:iec958-stereo";
        }
      ];
    };
  };

  environment.systemPackages = with pkgs; [
    alsa-utils
    libcamera
    pulseaudio
    usbutils
    v4l-utils
  ];

  virtualisation.vmVariant = {
    services.greetd.enable = lib.mkForce true;
    services.displayManager.sddm.enable = lib.mkForce false;
    programs.regreet.enable = lib.mkForce false;
    services.greetd.settings.initial_session = vmHyprlandSession;
    services.greetd.settings.default_session = vmHyprlandSession;

    virtualisation = {
      graphics = true;
      cores = 6;
      memorySize = 12288;
      diskSize = 65536;
      resolution = {
        x = 1920;
        y = 1080;
      };
    };

    services.qemuGuest.enable = true;
    services.xserver.videoDrivers = lib.mkForce [ "modesetting" ];
    users.users.ash.hashedPassword = lib.mkForce null;
    users.users.ash.password = lib.mkForce "ash";
    virtualisation.appvm.user = "ash";
  };

  systemd.tmpfiles.rules = [
    "L+ /home/example/games - - - - /srv/games"
    "L+ /home/example/piss_boi - - - - /mnt/bitlocker/piss_boi"
    "d /home/example/.local 0755 ash users - -"
    "d /home/example/.local/share 0755 ash users - -"
    "d /home/example/.local/share/Steam 0755 ash users - -"
    "d /home/example/.local/share/Steam/steamapps 0755 ash users - -"
    "d ${steamBitlockerCompatData} 0755 ash users - -"
  ];

  systemd.timers = lib.genAttrs disabledTapeTimers (_: {
    enable = lib.mkForce false;
    wantedBy = lib.mkForce [ ];
  });
}
