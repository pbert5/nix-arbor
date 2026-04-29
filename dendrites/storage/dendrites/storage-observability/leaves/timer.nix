{ lib, pkgs, site, hostInventory, ... }:
let
  fabric = site.storageFabric or { };
  annexCfg = fabric.annex or { };
  repoRoot = annexCfg.repoRoot or "/srv/annex/cluster-data";
  annexUser = annexCfg.user or "annex";

  hasAnnex = builtins.any
    (r: builtins.elem r (hostInventory.roles or [ ]))
    [ "annex-storage" "annex-client" "annex-workstation" "annex-compute-cache" ];
in
lib.mkIf hasAnnex {
  # Daily copy-safety check: warn if any file has fewer than numcopies copies.
  systemd.services.annex-fsck-daily = {
    description = "Daily git-annex copy-safety check";
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    serviceConfig = {
      Type = "oneshot";
      User = annexUser;
      ExecStart = lib.getExe' pkgs.git-annex "git-annex" +
        " -C ${repoRoot} fsck --fast --jobs=2";
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
