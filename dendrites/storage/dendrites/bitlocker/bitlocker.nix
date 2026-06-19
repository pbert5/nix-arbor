{
  config,
  hostInventory,
  lib,
  pkgs,
  utils,
  ...
}:
let
  bitlockerOrg = lib.attrByPath [ "org" "storage" "bitlocker" ] { } hostInventory;
  volumes = bitlockerOrg.volumes or { };
  mountOwner = bitlockerOrg.mountOwner or "ash";
  mountGroup = bitlockerOrg.mountGroup or "users";
  configuredOwnerUid = lib.attrByPath [ "users" "users" mountOwner "uid" ] null config;
  configuredOwnerGid = lib.attrByPath [ "users" "groups" mountGroup "gid" ] null config;
  ownerUid = if configuredOwnerUid == null then 1000 else configuredOwnerUid;
  ownerGid = if configuredOwnerGid == null then 100 else configuredOwnerGid;

  escapeArgs = args: lib.concatMapStringsSep " " lib.escapeShellArg args;

  unlockServiceName = name: "bitlocker-unlock-${name}";
  unlockUnitName = name: "${unlockServiceName name}.service";
  mountServiceName = name: "bitlocker-mount-${name}";

  defaultMountOptions =
    volume:
    [
      "uid=${toString ownerUid}"
      "gid=${toString ownerGid}"
      "umask=0022"
      "windows_names"
    ]
    ++ lib.optionals (volume.readOnly or false) [ "ro" ];

  mountOptions = volume:
    if volume ? mountOptions then volume.mountOptions else defaultMountOptions volume;

  unlockScript =
    name: volume:
    pkgs.writeShellScript "bitlocker-unlock-${name}" ''
      set -eu

      mapper_name=${lib.escapeShellArg volume.mapperName}
      device=${lib.escapeShellArg volume.device}

      if [ -e "/dev/mapper/$mapper_name" ]; then
        exit 0
      fi

      for key_file in ${escapeArgs volume.keyFiles}; do
        if [ ! -r "$key_file" ]; then
          echo "bitlocker ${name}: missing recovery key file $key_file" >&2
          continue
        fi

        if ${pkgs.cryptsetup}/bin/cryptsetup open --batch-mode --type bitlk --key-file "$key_file" "$device" "$mapper_name"; then
          exit 0
        fi
      done

      echo "bitlocker ${name}: failed to unlock $device with the configured recovery keys" >&2
      exit 1
    '';
in
{
  boot.supportedFilesystems = [ "ntfs" ];

  environment.systemPackages = [ pkgs.cryptsetup ];

  systemd.tmpfiles.rules = builtins.map (
    volume: "d ${volume.mountPoint} 0755 root root - -"
  ) (builtins.attrValues volumes);

  systemd.services = lib.mapAttrs' (
    name: volume:
    lib.nameValuePair (unlockServiceName name) {
      description = "Unlock BitLocker volume ${name}";
      path = [ pkgs.coreutils pkgs.cryptsetup ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = unlockScript name volume;
        ExecStop = pkgs.writeShellScript "bitlocker-close-${name}" ''
          set -eu

          mapper_name=${lib.escapeShellArg volume.mapperName}

          if [ -e "/dev/mapper/$mapper_name" ]; then
            ${pkgs.cryptsetup}/bin/cryptsetup close "$mapper_name"
          fi
        '';
      };
    }
  ) volumes // lib.mapAttrs' (
    name: volume:
    lib.nameValuePair (mountServiceName name) {
      description = "Mount BitLocker volume ${name}";
      wantedBy = [ "multi-user.target" ];
      requires = [ (unlockUnitName name) ];
      after = [
        "local-fs.target"
        (unlockUnitName name)
        "systemd-tmpfiles-setup.service"
      ];
      path = with pkgs; [
        coreutils
        util-linux
      ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = pkgs.writeShellScript "bitlocker-mount-${name}" ''
          set -eu

          mount_point=${lib.escapeShellArg volume.mountPoint}

          if ${pkgs.util-linux}/bin/findmnt -rn "$mount_point" >/dev/null 2>&1; then
            ${lib.optionalString (!(volume.readOnly or false)) ''
              ${pkgs.util-linux}/bin/mount \
                -o ${lib.escapeShellArg ("remount," + lib.concatStringsSep "," (mountOptions volume))} \
                "$mount_point"
            ''}
            exit 0
          fi

          ${pkgs.util-linux}/bin/mount \
            -t ${lib.escapeShellArg (volume.fsType or "ntfs3")} \
            -o ${lib.escapeShellArg (lib.concatStringsSep "," (mountOptions volume))} \
            ${lib.escapeShellArg "/dev/mapper/${volume.mapperName}"} \
            "$mount_point"
        '';
        ExecStop = pkgs.writeShellScript "bitlocker-umount-${name}" ''
          set -eu

          mount_point=${lib.escapeShellArg volume.mountPoint}

          if ${pkgs.util-linux}/bin/findmnt -rn "$mount_point" >/dev/null 2>&1; then
            ${pkgs.util-linux}/bin/umount "$mount_point"
          fi
        '';
      };
    }
  ) volumes;
}
