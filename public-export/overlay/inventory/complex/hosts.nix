{
  inputs ? null,
}:
{
  workstation-1 = {
    exported = true;
    system = "x86_64-linux";
    dendrites = [
      "base"
      "dev-tools"
      "system/workstation"
      "desktop/gnome"
      "media/game-library"
    ];
    fruits = [ ];
    users = [
      "user1"
      "user2"
    ];
    facts = { };
    org.network.membership.optIn = "all";
    hardwareModules = [
      ../../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
    overrides = [ ];
  };

  storage-1 = {
    exported = true;
    system = "x86_64-linux";
    dendrites = [
      "base"
      "dev-tools"
      "system/workstation"
      "storage/zfs"
      "storage/git-annex"
      "storage/seaweedfs-hot"
      "storage/archive"
      "storage/storage-observability"
      "network/radicle"
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
    org.network.membership.optIn = "all";
    org.storage.zfs.linkedUsers = [ "user1" ];
    org.storage.annex = {
      group = "archive";
      fabric = {
        storage = true;
        archive = true;
      };
      archive.nas = {
        enable = true;
        path = "/tank/archive";
      };
    };
    org.network.radicle = {
      seed = true;
      privateKeyFile = "/var/lib/radicle/keys/radicle";
      repos = [
        "flake-public"
        "cluster-data"
      ];
    };
    org.storage.seaweedfs = {
      master = true;
      volume = true;
      filer = true;
    };
    org.storage.observability.enable = true;
    hardwareModules = [
      ../../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
    overrides = [ ];
  };

  library-1 = {
    exported = true;
    system = "x86_64-linux";
    dendrites = [
      "base"
      "dev-tools"
      "system/workstation"
      "storage/tape"
      "storage/archive"
      "network/radicle"
    ];
    fruits = [ "fossilsafe" ];
    users = [ "user1" ];
    facts.storage.tape.devices = {
      changer = "/dev/tape/by-id/REPLACE_ME";
      drive = "/dev/tape/by-id/REPLACE_ME";
      drives = [ "/dev/tape/by-id/REPLACE_ME" ];
    };
    org.network.membership.optIn = "all";
    org.storage.tape = {
      manager = "fossilsafe";
      fossilsafe = {
        stateDir = "/var/lib/fossilsafe";
        openFirewall = false;
      };
    };
    org.storage.annex = {
      group = "archive";
      fabric.archive = true;
      archive.tape.enable = true;
    };
    org.network.radicle = {
      seed = true;
      privateKeyFile = "/var/lib/radicle/keys/radicle";
      repos = [ "cluster-data" ];
    };
    hardwareModules = [
      ../../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
    overrides = [ ];
  };
}
