{ lib, site, hostInventory, ... }:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  archiveCfg = fabric.archive or { };
  minCopies = archiveCfg.minArchiveCopies or 2;
  annexUser = annexCfg.user or "annex";
  annexGroup = annexCfg.group or "annex";
  isArchiveNode = builtins.elem "archive-node" (hostInventory.roles or [ ]);
  archiveOrg = lib.attrByPath [ "org" "storage" "annex" "archive" ] { } hostInventory;
  hasNas = archiveOrg.nas.enable or false;
  hasTape = archiveOrg.tape.enable or false;
  hasObject = archiveOrg.object.enable or false;
  hasRemovable = archiveOrg.removableDisk.enable or false;
in
lib.mkIf isArchiveNode {
  assertions = [
    {
      assertion = hasNas || hasTape || hasObject || hasRemovable;
      message = ''
        Host claims role "archive-node" but no archive backend is enabled.
        Set at least one of:
          org.storage.annex.archive.nas.enable = true;
          org.storage.annex.archive.tape.enable = true;
          org.storage.annex.archive.object.enable = true;
          org.storage.annex.archive.removableDisk.enable = true;
      '';
    }
  ];

  systemd.tmpfiles.rules = [
    "d /srv/annex/archive 0750 ${annexUser} ${annexGroup} - -"
  ];
}
