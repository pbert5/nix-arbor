{
  name = "network/tailscale";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [ "tailscale-underlay" ];
  requires = [ "network" ];
  conflicts = [ ];
  hostClasses = [ ];
}
