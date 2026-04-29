{
  name = "storage/seaweedfs-hot";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "seaweedfs-hot-pool"
    "seaweedfs-master"
    "seaweedfs-volume"
    "seaweedfs-filer"
    "seaweedfs-s3"
  ];
  requires = [ "storage" ];
  conflicts = [ ];
  hostClasses = [
    "seaweed-master"
    "seaweed-volume"
    "seaweed-filer"
    "seaweed-s3"
  ];
}
