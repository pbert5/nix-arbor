{
  name = "desktop/hydrus";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [ "hydrus-desktop" ];
  requires = [
    "desktop"
    "desktop/hyprland"
  ];
  conflicts = [ ];
}
