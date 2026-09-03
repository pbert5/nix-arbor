{ lib, pkgs, ... }:
{
  users.users.ash.extraGroups = lib.mkAfter [
    "audio"
    "video"
  ];

  home-manager.users.ash = {
    services.kanshi = {
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

    systemd.user.services.kanshi.Unit.ConditionEnvironment = lib.mkForce [
      "WAYLAND_DISPLAY"
      "XDG_CURRENT_DESKTOP=niri"
    ];
  };

  services.pipewire.wireplumber.extraConfig = {
    "10-blue-microphone-profile" = {
      "monitor.alsa.rules" = [
        {
          matches = [
            { "device.name" = "~alsa_card.usb-Generic_Blue_Microphones.*"; }
          ];
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
}
