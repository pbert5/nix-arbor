{
  config,
  lib,
  pkgs,
  ...
}:
let
  backupLxdRoot = "big/backup/r640-0/mypool/lxd";
  gameLibraryAnnexPath = lib.makeBinPath [
    pkgs.git
    pkgs.git-annex
  ] + ":/run/current-system/sw/bin";
  gameLibraryAnnexEnableIroh = pkgs.writeShellScript "game-library-annex-enable-iroh" ''
    set -euo pipefail

    export HOME=/home/example
    export PATH=${lib.escapeShellArg gameLibraryAnnexPath}

    exec ${lib.getExe pkgs.git-annex} p2p --enable iroh
  '';
  gameLibraryAnnexStopDaemons = pkgs.writeShellScript "game-library-annex-stop-daemons" ''
    set -euo pipefail

    for proc in /proc/[0-9]*; do
      pid=''${proc##*/}

      if [ "$(readlink "$proc/cwd" 2>/dev/null || true)" != "/big/GameLibrary" ]; then
        continue
      fi

      cmdline="$(tr '\0' ' ' < "$proc/cmdline" 2>/dev/null || true)"
      case "$cmdline" in
        *git-annex*remotedaemon* | *git-annex-p2p-iroh* | *dumbpipe*)
          kill "$pid" 2>/dev/null || true
          ;;
      esac
    done
  '';
  gameLibraryAnnexStartDaemon = pkgs.writeShellScript "game-library-annex-start-daemon" ''
    set -euo pipefail

    export HOME=/home/example
    export PATH=${lib.escapeShellArg gameLibraryAnnexPath}

    exec ${lib.getExe pkgs.git-annex} remotedaemon
  '';
in
{
  networking.hostName = "t320-0";

  # EFI boot from the dedicated 185.8G root SSD (/dev/sdf after partitioning).
  # The large ZFS data disks stay in place and are imported separately.
  boot.loader.grub.enable = lib.mkForce false;
  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 10;
  boot.loader.efi.canTouchEfiVariables = true;

  # Import the healthy secondary data pool in addition to `big` (handled by storage/zfs dendrite).
  # The preserved `small` pool is intentionally not auto-imported because the
  # live pool currently reports FAULTED/UNAVAIL and should be repaired first.
  boot.zfs.extraPools = [ "fast" ];

  # This host boots from a plain ext4 root partition, not from LVM. Leaving
  # host-side LVM scanning enabled makes systemd try to auto-activate stale VGs
  # discovered inside read-only backup zvols, which marks the machine degraded.
  services.lvm.enable = false;

  # t320-0 is reachable during deployment even when NetworkManager does not
  # report a fully online state within the wait-online timeout.
  systemd.services.NetworkManager-wait-online.enable = lib.mkForce false;

  # Replicated backup datasets from the old TrueNAS layout inherit read-only
  # parents under /big/backup. Mark the nested LXD datasets as `noauto` before
  # zfs-mount runs so activation does not try to create child mountpoints inside
  # a read-only backup tree.
  systemd.services.zfs-mount.serviceConfig.ExecStartPre = [
    "${pkgs.writeShellScript "t320-0-zfs-mount-pre" ''
      set -euo pipefail

      if ! ${config.boot.zfs.package}/sbin/zfs list -H ${lib.escapeShellArg backupLxdRoot} >/dev/null 2>&1; then
        exit 0
      fi

      ${config.boot.zfs.package}/sbin/zfs list -H -r -t filesystem -o name ${lib.escapeShellArg backupLxdRoot} \
        | ${pkgs.gnused}/bin/sed 1d \
        | while IFS= read -r dataset; do
          [ -n "$dataset" ] || continue

          if [ "$(${config.boot.zfs.package}/sbin/zfs get -H -o value canmount "$dataset")" != "noauto" ]; then
            ${config.boot.zfs.package}/sbin/zfs set canmount=noauto "$dataset"
          fi
        done
    ''}"
  ];

  users.users.ash.uid = 1000;
  users.users.ash.linger = true;
  users.groups.home-share = { };
  users.users.ash.extraGroups = [ "home-share" ];
  users.users.madeline.extraGroups = [ "home-share" ];

  security.sudo.extraRules = [
    {
      users = [ "ash" ];
      commands = [
        {
          command = "${pkgs.git-annex}/bin/.git-annex-wrapped enable-tor 1000";
          options = [
            "SETENV"
            "NOPASSWD"
          ];
        }
      ];
    }
  ];

  systemd.tmpfiles.rules = [
    "z /home/example 2750 ash home-share - -"
    "z /home/example 2750 madeline home-share - -"
    "z /big/GameLibrary 2775 ash home-share - -"
    "z /fast/GameLibrary 2775 ash home-share - -"
    "z /fast/GameLibrary/.git 2775 ash home-share - -"
    "z /fast/GameLibrary/.git/annex 2775 ash home-share - -"
    "z /fast/GameLibrary/.git/annex/creds 2770 ash home-share - -"
    "Z /fast/GameLibrary/.git - ash home-share - -"
    "Z /fast/GameLibrary/_source-archives - ash home-share - -"
    "Z /fast/GameLibrary/incoming - ash home-share - -"
    "Z /fast/GameLibrary/roms - ash home-share - -"
    "L+ /home/example/big - - - - /big"
    "L+ /home/example/fast - - - - /fast"
    "L+ /home/example/big - - - - /big"
    "L+ /home/example/fast - - - - /fast"
  ];

  systemd.services.game-library-annex-remotedaemon = {
    description = "GameLibrary git-annex P2P remote daemon";
    wantedBy = [ "multi-user.target" ];
    after = [
      "network-online.target"
      "tor.service"
    ];
    wants = [
      "network-online.target"
      "tor.service"
    ];
    environment = {
      HOME = "/home/example";
    };
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = "ash";
      Group = "home-share";
      WorkingDirectory = "/big/GameLibrary";
      ExecStartPre = [
        gameLibraryAnnexStopDaemons
        gameLibraryAnnexEnableIroh
      ];
      ExecStart = gameLibraryAnnexStartDaemon;
    };
  };

  home-manager.users.ash = {
    programs.git.settings.safe.directory = [
      "/big/GameLibrary"
      "/fast/GameLibrary"
    ];

    programs.btop = {
      enable = true;
      settings = {
        # ZFS pools are mounted by ZFS services rather than /etc/fstab, so the
        # fstab-only default hides everything except / and /boot on this host.
        use_fstab = false;
        only_physical = false;
        zfs_hide_datasets = true;
        disks_filter = "/ /boot /big /fast";
      };
    };
  };

  home-manager.users.madeline = {
    programs.git.settings.safe.directory = [
      "/big/GameLibrary"
      "/fast/GameLibrary"
    ];
  };
}
