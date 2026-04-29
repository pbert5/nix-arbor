{ lib, site, ... }:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  repoRoot = annexCfg.repoRoot or "/srv/annex/cluster-data";
  annexUser = annexCfg.user or "annex";
  annexGroup = annexCfg.group or "annex";
in
{
  systemd.tmpfiles.rules = [
    # Annex repo root and canonical sub-directories.
    "d ${repoRoot}               0750 ${annexUser} ${annexGroup} - -"
    "d ${repoRoot}/datasets       0750 ${annexUser} ${annexGroup} - -"
    "d ${repoRoot}/projects       0750 ${annexUser} ${annexGroup} - -"
    "d ${repoRoot}/outputs        0750 ${annexUser} ${annexGroup} - -"
    "d ${repoRoot}/models         0750 ${annexUser} ${annexGroup} - -"
    "d ${repoRoot}/manifests      0750 ${annexUser} ${annexGroup} - -"
    "d ${repoRoot}/scratch        0750 ${annexUser} ${annexGroup} - -"
    "d ${repoRoot}/archive        0750 ${annexUser} ${annexGroup} - -"
  ];
}
