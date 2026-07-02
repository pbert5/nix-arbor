{
  gameLibrary = {
    fsType = "nfs";
    group = "home-share";
    groupId = 993;
    mode = "0775";
    mountPoint = "/srv/games";
    options = [
      "nofail"
      "_netdev"
      "x-systemd.automount"
      "x-systemd.idle-timeout=600"
      "nfsvers=4.2"
    ];
    source = "t320-0-ygg:/big/GameLibrary";
    localPath = "/big/GameLibrary";
    export = {
      hosts = [
        "r640-0-ygg"
        "desktoptoodle-ygg"
      ];
      options = [
        "rw"
        "crossmnt"
        "no_subtree_check"
      ];
    };
  };

  backupPlans = {
    game_backup = import ./backup-plans/game_backup.nix;
  };
}
