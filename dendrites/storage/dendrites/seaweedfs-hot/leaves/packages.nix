{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    seaweedfs
    fuse
    fuse3
  ];

  users.groups.seaweedfs = { };
  users.users.seaweedfs = {
    isSystemUser = true;
    group = "seaweedfs";
    description = "SeaweedFS service account";
  };
}
