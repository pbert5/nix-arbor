{
  name = "desktop/cinnamon";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [ "cinnamon-desktop" ];
  requires = [ "desktop" ];
  conflicts = [ "desktop/gnome" ];
  hostClasses = [ "workstation" ];
}
