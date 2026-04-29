{ site, ... }:
let
  gameLibrary = site.storage.gameLibrary;
in
{
  users.groups.${gameLibrary.group}.gid = gameLibrary.groupId;

  fileSystems.${gameLibrary.mountPoint} = {
    device = gameLibrary.source;
    fsType = gameLibrary.fsType;
    options = gameLibrary.options;
  };

  systemd.tmpfiles.rules = [
    "d ${gameLibrary.mountPoint} ${gameLibrary.mode} root ${gameLibrary.group} - -"
  ];
}
