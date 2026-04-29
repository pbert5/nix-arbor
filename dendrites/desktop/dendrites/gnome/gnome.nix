{ ... }:
{
  hardware.bluetooth.enable = true;
  hardware.graphics.enable = true;

  programs.dconf.enable = true;

  security.rtkit.enable = true;

  services.accounts-daemon.enable = true;
  services.displayManager.gdm.enable = true;
  services.blueman.enable = true;
  services.colord.enable = true;
  services.gnome.gnome-keyring.enable = true;
  services.gnome.gnome-settings-daemon.enable = true;
  services.gvfs.enable = true;
  services.libinput.enable = true;
  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
  };
  services.printing.enable = true;
  services.udisks2.enable = true;
  services.upower.enable = true;

  services.xserver.enable = true;

  services.desktopManager.gnome.enable = true;
}
