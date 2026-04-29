{ lib, site, hostInventory, ... }:
let
  annexCfg = lib.attrByPath [ "storageFabric" "annex" ] { } site;
  annexUser = annexCfg.user or "annex";
  annexGroup = annexCfg.group or "annex";
  archiveOrg = lib.attrByPath [ "org" "storage" "annex" "archive" ] { } hostInventory;
  nasOrg = archiveOrg.nas or { };
  nasEnable = nasOrg.enable or false;
  nasPath = nasOrg.path or "/srv/annex/archive/nas";
in
lib.mkIf nasEnable {
  systemd.tmpfiles.rules = [
    "d ${nasPath} 0750 ${annexUser} ${annexGroup} - -"
  ];

  # NAS annex remote is registered by the cluster-annex init script.
  # This leaf creates the directory and ensures it is reachable.
  # Mount configuration (NFS/ZFS) belongs in host overrides.
}
