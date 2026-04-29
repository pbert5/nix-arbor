{ hostInventory, lib, ... }:
let
  zfsConfig = lib.attrByPath [ "facts" "storage" "zfs" ] null hostInventory;
  hostId = lib.attrByPath [ "facts" "hostId" ] null hostInventory;
in
{
  boot.supportedFilesystems = lib.mkIf (zfsConfig != null) [ "zfs" ];
  boot.zfs.extraPools = lib.mkIf (zfsConfig != null) [ zfsConfig.poolName ];
  networking.hostId = lib.mkIf (hostId != null) hostId;
}
