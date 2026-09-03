{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.arbor.desktoptoodle.gamingBitlocker;
  mapperName = "bitlk-piss-boi";
  mountPoint = "/mnt/bitlocker/piss_boi";
  compatData = "/home/ash/.local/share/Steam/steamapps/compatdata-piss-boi";
  libraryCompatData = "${mountPoint}/games/steamapps/compatdata";
  ownedMarker = "/run/nix-arbor/bitlocker-pissBoi.opened";
  unlockUnit = "bitlocker-unlock-pissBoi.service";
  mountUnit = "bitlocker-mount-pissBoi.service";
  compatTargetUnit = "steam-bitlocker-compatdata-target.service";
  compatMountUnit = "mnt-bitlocker-piss_boi-games-steamapps-compatdata.mount";
  configuredDevice = if cfg.device == null then "" else cfg.device;
in
{
  options.arbor.desktoptoodle.gamingBitlocker = {
    enable = lib.mkEnableOption "the optional desktoptoodle piss_boi BitLocker game disk";

    # Deliberately unset: the disk identity must be confirmed on the target
    # host (prefer a /dev/disk/by-uuid path) before enabling this module.
    device = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Host-confirmed BitLocker block-device path for piss_boi.";
    };

    # These are names of host-local files, never secret values. Keep them out
    # of the Nix store and materialize them at runtime under this directory.
    keyFiles = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Runtime-only BitLocker recovery-key file paths.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.device != null;
        message = "desktoptoodle gaming BitLocker is enabled but its device path is unset; confirm the live device first.";
      }
      {
        assertion = cfg.keyFiles != [ ];
        message = "desktoptoodle gaming BitLocker is enabled but no runtime recovery-key paths were supplied.";
      }
    ];

    boot.supportedFilesystems = [ "ntfs" ];
    environment.systemPackages = [ pkgs.cryptsetup ];

    # Directory creation is harmless when the optional disk is absent. The
    # symlink intentionally remains useful once the disk is unlocked.
    systemd.tmpfiles.rules = [
      "d ${mountPoint} 0755 root root - -"
      "L /home/ash/piss_boi - - - - ${mountPoint}"
      "d /home/ash/.local 0755 ash users - -"
      "d /home/ash/.local/share 0755 ash users - -"
      "d /home/ash/.local/share/Steam 0755 ash users - -"
      "d /home/ash/.local/share/Steam/steamapps 0755 ash users - -"
      "d ${compatData} 0755 ash users - -"
    ];

    # This is intentionally a wanted service rather than a dependency of
    # local-fs.target: a missing/unconfigured game disk must not prevent boot.
    systemd.services = {
      bitlocker-unlock-pissBoi = {
        description = "Unlock the optional piss_boi BitLocker game disk";
        wantedBy = [ "multi-user.target" ];
        path = [
          pkgs.coreutils
          pkgs.cryptsetup
        ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          RuntimeDirectory = "nix-arbor";
          RuntimeDirectoryMode = "0700";
          ExecStart = pkgs.writeShellScript "bitlocker-unlock-pissBoi" ''
            set -eu
            mapper_name=${lib.escapeShellArg mapperName}
            device=${lib.escapeShellArg configuredDevice}

            if [ -e "/dev/mapper/$mapper_name" ]; then
              exit 0
            fi

            for key_file in ${lib.concatMapStringsSep " " lib.escapeShellArg cfg.keyFiles}; do
              if [ ! -r "$key_file" ]; then
                echo "bitlocker pissBoi: missing runtime recovery key $key_file" >&2
                continue
              fi
              if ${pkgs.cryptsetup}/bin/cryptsetup open --batch-mode \
                --type bitlk --key-file "$key_file" "$device" "$mapper_name"; then
                ${pkgs.coreutils}/bin/touch ${lib.escapeShellArg ownedMarker}
                exit 0
              fi
            done

            echo "bitlocker pissBoi: unable to unlock the configured device" >&2
            exit 1
          '';
          ExecStop = pkgs.writeShellScript "bitlocker-close-pissBoi" ''
            set -eu
            if [ -e ${lib.escapeShellArg ownedMarker} ] && [ -e /dev/mapper/${lib.escapeShellArg mapperName} ]; then
              ${pkgs.cryptsetup}/bin/cryptsetup close ${lib.escapeShellArg mapperName}
            fi
            ${pkgs.coreutils}/bin/rm -f ${lib.escapeShellArg ownedMarker}
          '';
        };
      };

      bitlocker-mount-pissBoi = {
        description = "Mount the optional piss_boi BitLocker game disk";
        wantedBy = [ "multi-user.target" ];
        requires = [ unlockUnit ];
        after = [
          "local-fs.target"
          unlockUnit
          "systemd-tmpfiles-setup.service"
        ];
        path = [
          pkgs.coreutils
          pkgs.util-linux
        ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = pkgs.writeShellScript "bitlocker-mount-pissBoi" ''
            set -eu
            mount_point=${lib.escapeShellArg mountPoint}
            if ${pkgs.util-linux}/bin/findmnt -rn "$mount_point" >/dev/null 2>&1; then
              exit 0
            fi
            owner_uid="$(${pkgs.coreutils}/bin/id -u ash)"
            owner_gid="$(${pkgs.coreutils}/bin/id -g ash)"
            ${pkgs.util-linux}/bin/mount -t ntfs3 \
              -o "uid=$owner_uid,gid=$owner_gid,umask=0077,windows_names" \
              /dev/mapper/${lib.escapeShellArg mapperName} "$mount_point"
          '';
          ExecStop = pkgs.writeShellScript "bitlocker-umount-pissBoi" ''
            set -eu
            mount_point=${lib.escapeShellArg mountPoint}
            if ${pkgs.util-linux}/bin/findmnt -rn "$mount_point" >/dev/null 2>&1; then
              ${pkgs.util-linux}/bin/umount "$mount_point"
            fi
          '';
        };
      };

      steam-bitlocker-compatdata-target = {
        description = "Prepare native Proton compatdata for the piss_boi Steam library";
        wantedBy = [ "multi-user.target" ];
        requires = [ mountUnit ];
        after = [
          mountUnit
          "systemd-tmpfiles-setup.service"
        ];
        before = [ compatMountUnit ];
        path = [ pkgs.coreutils ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          install -d -o ash -g users -m 0755 ${lib.escapeShellArg compatData}
          install -d -o ash -g users -m 0755 ${lib.escapeShellArg libraryCompatData}
        '';
      };
    };

    systemd.mounts = [
      {
        description = "Native Proton compatdata for the piss_boi Steam library";
        what = compatData;
        where = libraryCompatData;
        type = "none";
        options = "bind";
        unitConfig.DefaultDependencies = false;
        requires = [
          mountUnit
          compatTargetUnit
        ];
        after = [
          mountUnit
          compatTargetUnit
        ];
        before = [ "umount.target" ];
        conflicts = [ "umount.target" ];
        wantedBy = [ "multi-user.target" ];
      }
    ];

    # Steam itself remains available even while the optional BitLocker device
    # is locked or absent.  Enabling the mount integration is a separate,
    # operator-gated decision after its device and runtime key paths are known.
    home-manager.users.ash.ashesDesktopApps.sets = lib.mkAfter [ "desktop.gaming" ];
  };
}
