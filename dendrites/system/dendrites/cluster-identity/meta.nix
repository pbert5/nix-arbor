{
  name = "system/cluster-identity";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "live-cluster-identity-registry"
    "cluster-identity-agent"
  ];
  requires = [ "system" ];
  conflicts = [ ];
}
