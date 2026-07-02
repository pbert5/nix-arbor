{ ... }:
{
  hardware.bluetooth.enable = true;
  hardware.graphics.enable = true;

  programs.hyprland = {
    enable = true;
    withUWSM = true;
    xwayland.enable = true;
  };

  security.pam.services.hyprlock = { };
  security.pam.services.sddm.enableGnomeKeyring = true;
  security.rtkit.enable = true;

  services.accounts-daemon.enable = true;
  services.blueman.enable = true;
  services.colord.enable = true;
  services.gnome.gnome-keyring.enable = true;
  services.gvfs.enable = true;
  services.libinput.enable = true;
  services.displayManager = {
    defaultSession = "hyprland-uwsm";
    sddm = {
      enable = true;
      wayland.enable = true;
    };
  };
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
    wireplumber.enable = true;
  };
  services.printing.enable = true;
  services.udisks2.enable = true;
  services.upower.enable = true;
  environment.sessionVariables.NIXOS_OZONE_WL = "1";

  home-manager.sharedModules = [
    ./hyprland-home.nix
  ];
}
