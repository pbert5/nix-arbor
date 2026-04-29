{
  name = "system/distributed-builds";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [ "nix-distributed-builds" ];
  requires = [ "system" ];
  conflicts = [ ];
  hostClasses = [ ];
}
