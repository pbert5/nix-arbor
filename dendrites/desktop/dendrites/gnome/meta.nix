{
  name = "desktop/gnome";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [ "gnome-desktop" ];
  requires = [ "desktop" ];
  conflicts = [
    "desktop/cinnamon"
    "desktop/hyprland"
    "desktop/hyprland-minimal"
  ];
}
