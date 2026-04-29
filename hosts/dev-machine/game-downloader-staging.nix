{ config, pkgs, ... }:
let
  stageDir = "/srv/game-downloader-cache/incoming";
  spillDir = "/srv/game-downloader-cache/incoming-spill";
  stageSync = pkgs.writeShellScript "game-downloader-stage-sync" ''
    #!${pkgs.runtimeShell}
    set -euo pipefail

    mode="''${1:-}"
    cache_root="/srv/game-downloader-cache"
    stage_dir="${stageDir}"
    spill_dir="${spillDir}"

    if ! findmnt -rn "$cache_root" > /dev/null 2>&1; then
      echo "Skipping game downloader stage sync because $cache_root is not mounted." >&2
      exit 0
    fi

    if ! findmnt -rn "$stage_dir" > /dev/null 2>&1; then
      echo "Skipping game downloader stage sync because $stage_dir is not mounted." >&2
      exit 0
    fi

    mkdir -p "$stage_dir" "$spill_dir"

    has_entries() {
      local dir="$1"
      find "$dir" -mindepth 1 -print -quit | grep -q .
    }

    case "$mode" in
      restore)
        if ! has_entries "$spill_dir"; then
          exit 0
        fi

        echo "Restoring persisted game downloader staging data into tmpfs..."
        rsync -aH --remove-source-files "$spill_dir"/ "$stage_dir"/
        find "$spill_dir" -depth -type d -empty -delete
        ;;
      persist)
        if ! has_entries "$stage_dir"; then
          exit 0
        fi

        echo "Persisting RAM-backed game downloader staging data to disk..."
        rsync -aH --delete "$stage_dir"/ "$spill_dir"/
        ;;
      *)
        echo "usage: $0 <restore|persist>" >&2
        exit 2
        ;;
    esac
  '';
in
{
  fileSystems."/srv/game-downloader-cache" = {
    device = "/dev/disk/by-uuid/REDACTED-UUID";
    fsType = "ext4";
    options = [
      "nofail"
      "x-systemd.device-timeout=5s"
    ];
  };

  fileSystems.${stageDir} = {
    device = "tmpfs";
    fsType = "tmpfs";
    options = [
      "gid=${toString config.users.groups.home-share.gid}"
      "mode=2775"
      "nodev"
      "nosuid"
      "size=85%"
      "uid=${toString config.users.users.ash.uid}"
    ];
  };

  systemd.tmpfiles.rules = [
    "z ${stageDir} 2775 ash home-share - -"
    "d ${spillDir} 2775 ash home-share - -"
  ];

  systemd.services.game-downloader-stage-restore = {
    description = "Restore persisted game downloader staging data into tmpfs";
    after = [
      "local-fs.target"
      "systemd-tmpfiles-setup.service"
    ];
    wantedBy = [ "multi-user.target" ];
    path = with pkgs; [
      coreutils
      findutils
      gnugrep
      rsync
      util-linux
    ];
    serviceConfig = {
      Type = "oneshot";
      TimeoutStartSec = "15min";
    };
    script = ''
      exec ${stageSync} restore
    '';
  };

  systemd.services.game-downloader-stage-persist = {
    description = "Persist RAM-backed game downloader staging data before shutdown";
    wantedBy = [
      "halt.target"
      "kexec.target"
      "poweroff.target"
      "reboot.target"
    ];
    after = [ "local-fs.target" ];
    before = [
      "shutdown.target"
      "umount.target"
    ];
    path = with pkgs; [
      coreutils
      findutils
      gnugrep
      rsync
      util-linux
    ];
    unitConfig.DefaultDependencies = "no";
    serviceConfig = {
      Type = "oneshot";
      TimeoutStartSec = "15min";
    };
    script = ''
      exec ${stageSync} persist
    '';
  };
}
