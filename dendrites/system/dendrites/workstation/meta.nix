{
  name = "system/workstation";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [ "workstation-system" ];
  requires = [ "system" ];
  conflicts = [ "system/compute-worker" ];
  hostClasses = [ "workstation" ];
}
