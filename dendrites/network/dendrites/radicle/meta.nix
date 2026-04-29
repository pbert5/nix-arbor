{
  name = "network/radicle";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "radicle-node"
    "radicle-seed"
    "decentralized-git-mirror"
  ];
  requires = [ "network" ];
  conflicts = [ ];
  hostClasses = [ "radicle-seed" ];
}
