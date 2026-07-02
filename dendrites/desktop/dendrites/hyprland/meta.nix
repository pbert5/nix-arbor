{
  name = "desktop/hyprland";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [ "hyprland-desktop" ];
  requires = [ "desktop" ];
  conflicts = [
    "desktop/cinnamon"
    "desktop/gnome"
    "desktop/hyprland-minimal"
  ];
  cheatsheets.fileRegex = "^cheats/.*\\.cheat$";
}
