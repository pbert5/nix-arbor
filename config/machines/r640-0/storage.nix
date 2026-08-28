{
  config,
  lib,
  pkgs,
  ...
}:
{
  # r640 boots from ext4; this is an existing data pool. NixOS imports it,
  # but never creates, formats, renames, or destroys it.
  networking.hostId = "cbda65de";
  boot.supportedFilesystems = [ "zfs" ];
  boot.zfs.extraPools = [ "mypool" ];
  boot.zfs.forceImportRoot = false;
  boot.zfs.forceImportAll = false;

  systemd.services.zfs-home-links = {
    description = "Expose existing mypool directories to r640 users";
    wantedBy = [ "multi-user.target" ];
    after = [
      "zfs-import-mypool.service"
      "zfs-mount.service"
      "systemd-tmpfiles-setup.service"
    ];
    wants = [ "zfs-mount.service" ];
    serviceConfig.Type = "oneshot";
    script = ''
      set -eu
      pool_root=/mypool
      if ! ${config.boot.zfs.package}/sbin/zpool list -H mypool >/dev/null 2>&1; then
        echo "mypool is unavailable; leaving homes untouched"
        exit 0
      fi
      [ -d "$pool_root" ] || exit 0
      echo "mypool is mounted; no dataset links are inferred without live topology"
    '';
  };
}
