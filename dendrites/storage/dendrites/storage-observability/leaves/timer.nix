{
  lib,
  pkgs,
  site,
  hostInventory,
  hostName,
  ...
}:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  repoRoot = annexCfg.repoRoot or "/srv/annex/cluster-data";
  annexUser = annexCfg.user or "annex";

  annexFabric = lib.attrByPath [ "org" "storage" "annex" "fabric" ] { } hostInventory;
  hasAnnex =
    (annexFabric.storage or false)
    || (annexFabric.client or false)
    || (annexFabric.workstation or false)
    || (annexFabric.computeCache or false);
in
lib.mkIf hasAnnex {
  # Daily copy-safety check: warn if any file has fewer than numcopies copies.
  systemd.services.annex-fsck-daily = {
    description = "Daily git-annex copy-safety check";
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    path = with pkgs; [
      git
      git-annex
    ];
    environment = {
      HOME = repoRoot;
      GIT_AUTHOR_NAME = "${hostName}-annex";
      GIT_AUTHOR_EMAIL = "${hostName}-annex@local";
      GIT_COMMITTER_NAME = "${hostName}-annex";
      GIT_COMMITTER_EMAIL = "${hostName}-annex@local";
    };
    serviceConfig = {
      Type = "oneshot";
      User = annexUser;
      ExecStart = lib.getExe' pkgs.git "git" + " -C ${repoRoot} annex fsck --fast --jobs=2";
    };
  };

  systemd.timers.annex-fsck-daily = {
    description = "Daily git-annex copy-safety check timer";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "daily";
      RandomizedDelaySec = "1h";
      Persistent = true;
    };
  };
}
