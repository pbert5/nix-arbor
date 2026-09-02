{
  config,
  lib,
  pkgs,
  ...
}:
let
  poolRoot = "/mypool";
  dockerDataRoot = "${poolRoot}/docker_data";
  nixBuildDir = "${poolRoot}/nix-build";
  storageDirectories = "mypool-storage-directories.service";
in
{
  # r640 boots from ext4; this is an existing data pool. NixOS imports it,
  # but never creates, formats, renames, or destroys it.
  networking.hostId = "cbda65de";
  boot.supportedFilesystems = [ "zfs" ];
  boot.zfs.extraPools = [ "mypool" ];
  boot.zfs.forceImportRoot = false;
  boot.zfs.forceImportAll = false;

  # These paths must never be created on the root filesystem when the pool is
  # unavailable.  Keep creation behind a failing oneshot so consumers cannot
  # silently fall back to /mypool on the root filesystem.
  systemd.services.mypool-storage-directories = {
    description = "Create r640 directories on the mounted mypool";
    wantedBy = [ "multi-user.target" ];
    after = [
      "zfs-import-mypool.service"
      "zfs-mount.service"
    ];
    requires = [
      "zfs-import-mypool.service"
      "zfs-mount.service"
    ];
    serviceConfig.Type = "oneshot";
    script = ''
      set -eu
      ${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}
      ${pkgs.coreutils}/bin/install -d -o root -g root -m 0700 ${dockerDataRoot}
      ${pkgs.coreutils}/bin/install -d -o root -g nixbld -m 1770 ${nixBuildDir}
    '';
  };

  virtualisation.docker.daemon.settings = {
    "data-root" = dockerDataRoot;
    "storage-driver" = "zfs";
    "storage-opts" = [ "zfs.fsname=mypool/docker_data" ];
  };
  nix.settings = {
    build-dir = nixBuildDir;
    build-users-group = "nixbld";
  };

  # Docker is socket-activated, so ordering alone is insufficient: require
  # the pool directory service and check the mount at every daemon start.
  systemd.services.docker = {
    path = [ pkgs.zfs pkgs.nftables ];
    requires = [ storageDirectories ];
    after = [ storageDirectories ];
    serviceConfig.ExecStartPre = "${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}";
  };

  systemd.services.nix-daemon = {
    requires = [ storageDirectories ];
    after = [ storageDirectories ];
    serviceConfig.ExecStartPre = "${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}";
  };

  assertions = [
    {
      assertion = config.boot.zfs.extraPools == [ "mypool" ];
      message = "r640-0 must import only the existing mypool data pool";
    }
    {
      assertion = !config.boot.zfs.forceImportRoot && !config.boot.zfs.forceImportAll;
      message = "r640-0 must not force ZFS imports";
    }
    {
      assertion = config.virtualisation.docker.daemon.settings."data-root" == dockerDataRoot;
      message = "r640-0 Docker data-root must remain on mypool";
    }
    {
      assertion = config.nix.settings.build-dir == nixBuildDir;
      message = "r640-0 Nix build-dir must remain on mypool";
    }
    {
      assertion = config.nix.settings.build-users-group == "nixbld";
      message = "r640-0 Nix builds must use the declared nixbld group";
    }
    {
      assertion = lib.elem storageDirectories config.systemd.services.docker.requires;
      message = "Docker must require the mounted mypool directory service";
    }
    {
      assertion = lib.elem storageDirectories config.systemd.services.nix-daemon.requires;
      message = "The Nix daemon must require the mounted mypool directory service";
    }
    {
      assertion = config.virtualisation.docker.daemon.settings."storage-driver" == "zfs";
      message = "r640-0 Docker storage driver must remain zfs on mypool";
    }
  ];

  # No VM/test path is redirected here: this repository currently declares no
  # host-owned VM storage path, and inventing one would risk the live pool.
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
      if ! ${config.boot.zfs.package}/sbin/zpool list -H mypool >/dev/null 2>&1; then
        echo "mypool is unavailable; leaving homes untouched"
        exit 0
      fi
      [ -d ${poolRoot} ] || exit 0
      echo "mypool is mounted; no dataset links are inferred without live topology"
    '';
  };
}
