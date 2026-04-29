{ ... }:
{
  hardware.bluetooth.enable = true;
  hardware.graphics.enable = true;

  programs.dconf.enable = true;
  services.displayManager.defaultSession = "cinnamon";

  security.rtkit.enable = true;

  services.accounts-daemon.enable = true;
  services.blueman.enable = true;
  services.colord.enable = true;
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

  services.xserver = {
    enable = true;
    displayManager.lightdm.enable = true;
    desktopManager.cinnamon.enable = true;
  };
}
