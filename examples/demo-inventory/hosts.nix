{
  workstation-1 = {
    exported = true;
    system = "x86_64-linux";
    roles = [ "workstation" ];
    networks = [
      "privateYggdrasil"
      "tailscale"
    ];
    publicYggdrasil = false;
    dendrites = [
      "desktop/gnome"
      "media/game-library"
    ];
    fruits = [ ];
    users = [
      "user1"
      "user2"
    ];
    facts = { };
    org = { };
    hardwareModules = [ ];
    overrides = [ ];
  };

  storage-1 = {
    exported = true;
    system = "x86_64-linux";
    roles = [
      "workstation"
      "annex-storage"
      "seaweed-master"
      "seaweed-volume"
      "seaweed-filer"
      "archive-node"
      "storage-fabric-observer"
    ];
    networks = [
      "privateYggdrasil"
      "tailscale"
    ];
    publicYggdrasil = false;
    dendrites = [
      "storage/zfs"
      "storage/git-annex"
      "storage/seaweedfs-hot"
      "storage/archive"
      "storage/storage-observability"
    ];
    fruits = [ ];
    users = [ "user1" ];
    facts = {
      hostId = "deadbeef";
      storage.zfs = {
        poolName = "tank";
        rootMountPoint = "/tank";
      };
    };
    org.storage.zfs.linkedUsers = [ "user1" ];
    org.storage.annex = {
      group = "archive";
      archive.nas = {
        enable = true;
        path = "/tank/archive";
      };
    };
    hardwareModules = [ ];
    overrides = [ ];
  };
}
