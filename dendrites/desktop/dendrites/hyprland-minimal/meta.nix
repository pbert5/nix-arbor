{
  name = "desktop/hyprland-minimal";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [ "hyprland-minimal-desktop" ];
  requires = [ "desktop" ];
  conflicts = [
    "desktop/cinnamon"
    "desktop/gnome"
    "desktop/hyprland"
  ];
}
