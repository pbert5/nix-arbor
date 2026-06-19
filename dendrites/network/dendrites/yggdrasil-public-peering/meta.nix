{
  name = "network/yggdrasil-public-peering";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "public-yggdrasil-peering"
    "no-tun-yggdrasil-peering"
  ];
  requires = [ "network" ];
  conflicts = [ ];
}
