{
  name = "storage/zfs";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [
    "zfs"
    "zfs-pool-import"
  ];
  requires = [ "storage" ];
  conflicts = [ ];
  hostClasses = [ "workstation" ];
}
