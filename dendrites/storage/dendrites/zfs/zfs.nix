{ hostInventory, lib, ... }:
let
  zfsConfig = lib.attrByPath [ "facts" "storage" "zfs" ] null hostInventory;
  hostId = lib.attrByPath [ "facts" "hostId" ] null hostInventory;
in
{
  boot.supportedFilesystems = lib.mkIf (zfsConfig != null) [ "zfs" ];
  boot.zfs.extraPools = lib.mkIf (zfsConfig != null) [ zfsConfig.poolName ];
  # Preserve the pre-26.11 import behavior explicitly during the 26.05 upgrade.
  boot.zfs.forceImportRoot = lib.mkIf (zfsConfig != null) true;
  networking.hostId = lib.mkIf (hostId != null) hostId;
}
