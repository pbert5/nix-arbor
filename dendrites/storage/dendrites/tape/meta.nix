{
  name = "storage/tape";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [
    "tape-storage"
    "ltfs"
    "yatm" #todo: should probobly have another sub dendrite for either yatm or fossilsafe, easier way to split, and just set them as incompatible with one another 
  ];
  requires = [ "storage" ];
  conflicts = [ ];
  hostClasses = [ "workstation" ];
}
