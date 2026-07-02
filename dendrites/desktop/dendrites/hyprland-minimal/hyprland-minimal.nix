{ lib, pkgs, ... }:
let
  greeterCommand = pkgs.writeShellScript "hyprland-minimal-greeter" ''
    exec ${lib.getExe pkgs.tuigreet} \
      --time \
      --remember \
      --cmd "${lib.getExe pkgs.uwsm} start hyprland.desktop"
  '';
in
{
  hardware.graphics.enable = true;

  programs.hyprland = {
    enable = true;
    withUWSM = true;
    xwayland.enable = true;
  };

  security.polkit.enable = true;
  security.rtkit.enable = true;

  services.greetd = {
    enable = true;
    settings.default_session = {
      command = greeterCommand;
      user = "greeter";
    };
  };

  services.dbus.enable = true;
  services.libinput.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
    wireplumber.enable = true;
  };

  environment.sessionVariables.NIXOS_OZONE_WL = "1";
  environment.systemPackages = [
    pkgs.tuigreet
    pkgs.kitty
    pkgs.rofi
  ];

  home-manager.sharedModules = [ ./hyprland-minimal-home.nix ];
}
