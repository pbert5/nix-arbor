{
  name = "network/yggdrasil-private";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [
    "private-yggdrasil-mesh"
    "inventory-driven-overlay"
  ];
  requires = [ "network" ];
  conflicts = [ ];
  hostClasses = [ ];
}
