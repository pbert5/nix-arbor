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
    source = "t320-truenas-scale:/mnt/big/GameLibrary";
  };
}