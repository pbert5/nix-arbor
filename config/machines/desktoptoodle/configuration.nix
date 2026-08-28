{
  config,
  inputs,
  lib,
  pkgs,
  ...
}:
{
  imports = [
    ../../sops.nix
    inputs.sops-nix.nixosModules.sops
    ../../users
  ];

  # Preserve the legacy desktop behavior here while the shared profile stays
  # compositional. See docs/migrations/desktoptoodle-swap-over.md for the
  # intentionally unported storage and cluster services.
  networking.hostName = "desktoptoodle";
  networking.networkmanager.enable = true;

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };

  services.tailscale = {
    enable = true;
    useRoutingFeatures = "client";
    extraSetFlags = [ "--accept-dns=false" ];
  };

  virtualisation.docker.enable = true;

  arbor.environment.secrets = {
    enable = true;
    provider = "external-files";
  };

  boot.kernelPackages = pkgs.linuxPackages_6_18;
  boot.blacklistedKernelModules = [ "nouveau" ];
  boot.kernelModules = [ "uvcvideo" ];

  services.xserver.videoDrivers = [ "nvidia" ];
  hardware.nvidia = {
    modesetting.enable = true;
    nvidiaSettings = true;
    open = false;
    package = config.boot.kernelPackages.nvidiaPackages.legacy_580;
  };

  users.users.ash.extraGroups = [
    "audio"
    "video"
  ];

  home-manager.users.ash.desktop.hyprland.pointerSensitivity = -0.6;
  home-manager.users.ash.services.kanshi = {
    enable = true;
    settings = [
      {
        profile = {
          name = "desktoptoodle-dual";
          outputs = [
            {
              criteria = "LG Electronics LG ULTRAGEAR 411MXWE3J993";
              position = "0,0";
            }
            {
              criteria = "Acer Technologies ED340CU J0 55040A6463W01";
              position = "2560,0";
            }
          ];
        };
      }
    ];
  };

  home-manager.users.ash.systemd.user.services.kanshi.Unit.ConditionEnvironment = lib.mkForce [
    "WAYLAND_DISPLAY"
    "XDG_CURRENT_DESKTOP=niri"
  ];

  # The USB Blue microphone exposes its capture stream as iec958-stereo.
  services.pipewire.wireplumber.extraConfig."10-blue-microphone-profile" = {
    "monitor.alsa.rules" = [
      {
        matches = [ { "device.name" = "~alsa_card.usb-Generic_Blue_Microphones.*"; } ];
        actions.update-props."device.profile" = "output:iec958-stereo+input:iec958-stereo";
      }
    ];
  };

  environment.systemPackages = with pkgs; [
    alsa-utils
    btop
    curl
    fd
    fzf
    gh
    git
    jq
    libcamera
    neovim
    nh
    nil
    nix-tree
    nixfmt-rfc-style
    openssh
    pulseaudio
    ripgrep
    rsync
    tailscale
    tmux
    usbutils
    v4l-utils
    vim
    wget
  ];

  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 20;
  boot.loader.efi.canTouchEfiVariables = lib.mkDefault true;
}
