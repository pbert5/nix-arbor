{
  config,
  lib,
  hostInventory,
  pkgs,
  ...
}:
let
  zfsPool = lib.attrByPath [ "facts" "storage" "zfs" ] null hostInventory;
  zfsImportService =
    if zfsPool == null then
      null
    else
      "zfs-import-${zfsPool.poolName}.service";
  linkedUsers = lib.attrByPath [ "org" "storage" "zfs" "linkedUsers" ] [ ] hostInventory;
in
{
  networking.hostName = "r640-0";

  boot.loader.grub.enable = lib.mkForce false;
  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 10;
  boot.loader.efi.canTouchEfiVariables = true; #TODO: this entire thing could just be centralized as a boottype= efi in the host inventory and then config moved to a boot/efi dendrite same for other boot types used in other hosts

  users.users.ash.uid = 1000; #TODO: this should be specified in inventory instead of hard coded here
  users.users.ash.linger = true; #TODO: if this is present in every host config, we should just set in in the user class or something instead of having to remember to add it to every host config
  users.users.ash.extraGroups = [ "home-share" ];
  users.users.madeline.extraGroups = [ "home-share" ];
  home-manager.users.ash = { #this is good here
    programs.git.settings.user = {
      email = "user@example.com";
      name = "ash-r640-0";
    };
  };

  systemd.tmpfiles.rules = [
    "z /home/example 2750 ash home-share - -"
    "z /home/example 2750 madeline home-share - -"
    "L+ /home/example/games - - - - /srv/games"
    "L+ /home/example/flake - - - - /work/flake"
    "L+ /home/example/games - - - - /srv/games"
  ]; #TODO: this block is borderline standardized and should just be part of some dendrite

  systemd.services."zfs-import-${zfsPool.poolName}" = lib.mkIf (zfsPool != null) {
    serviceConfig.ExecCondition = "${pkgs.kmod}/bin/modinfo zfs";
  };

  systemd.services.zfs-home-links = lib.mkIf (zfsPool != null) { #TODO: all of this is just a function that should be taken care of by storage/zfs dendrite, and anything specific would be mentioned in the inventory
    description = "Link top-level ${zfsPool.poolName} directories into user homes";
    wantedBy = [ "multi-user.target" ];
    after = [
      "local-fs.target"
      zfsImportService
      "zfs-mount.service"
      "systemd-tmpfiles-setup.service"
    ];
    requires = [ zfsImportService ];
    wants = [ "zfs-mount.service" ];
    serviceConfig.Type = "oneshot";
    script = #TODO:  this just be a leaf of /work/flake/dendrites/storage/dendrites/zfs/zfs.nix
      let
        users = lib.concatStringsSep " " linkedUsers;
      in
      ''
        set -eu

        pool_name=${lib.escapeShellArg zfsPool.poolName}
        pool_root=${lib.escapeShellArg zfsPool.rootMountPoint}
        users="${users}"

        if ! ${config.boot.zfs.package}/sbin/zpool list -H "$pool_name" >/dev/null 2>&1; then
          echo "zfs-home-links: pool $pool_name is not imported yet, skipping"
          exit 0
        fi

        ${pkgs.coreutils}/bin/mkdir -p "$pool_root"

        if ! ${config.boot.zfs.package}/sbin/zfs mount -a; then
          echo "zfs-home-links: zfs mount -a reported a problem, continuing"
        fi

        if [ ! -d "$pool_root" ]; then
          echo "zfs-home-links: pool root $pool_root is not mounted yet, skipping"
          exit 0
        fi

        for entry in "$pool_root"/*; do
          [ -d "$entry" ] || continue

          name="$(basename "$entry")"

          for user in $users; do
            home_dir="/home/$user"
            destination="$home_dir/$name"

            [ -d "$home_dir" ] || continue

            if [ -L "$destination" ]; then
              target="$(${pkgs.coreutils}/bin/readlink "$destination")"
              if [ "$target" = "$entry" ]; then
                continue
              fi
              ${pkgs.coreutils}/bin/ln -sfn "$entry" "$destination"
              continue
            fi

            if [ -e "$destination" ]; then
              echo "zfs-home-links: leaving existing path in place: $destination"
              continue
            fi

            ${pkgs.coreutils}/bin/ln -s "$entry" "$destination"
          done
        done
      '';
  };
}
