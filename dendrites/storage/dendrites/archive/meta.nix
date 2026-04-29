{
  name = "storage/archive";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "annex-archive-remotes"
    "archive-nas"
    "archive-tape"
    "archive-object"
  ];
  requires = [ "storage" ];
  conflicts = [ ];
  hostClasses = [ "archive-node" ];
}
