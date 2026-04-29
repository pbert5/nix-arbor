{
  name = "system/compute-worker";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [ "compute-worker" ];
  requires = [ "system" ];
  conflicts = [ "system/workstation" ]; #TODO: would be easier to just say conflicts with other system sub dendrites as a blanket, so dont need to update this every time we add a new system sub dendrite, but for now this is fine since we only have one other system sub dendrite, and we can just remember to update this when we add more
  hostClasses = [ "compute-worker" ];
}
