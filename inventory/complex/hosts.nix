{
  inputs ? null,
}:
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
    hardwareModules = [
      ../../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
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
      "radicle-seed"
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
    org.storage.zfs.linkedUsers = [ "user1" ];
    org.storage.annex = {
      group = "archive";
      archive.nas = {
        enable = true;
        path = "/tank/archive";
      };
    };
    org.network.radicle = {
      privateKeyFile = "/var/lib/radicle/keys/radicle";
      repos = [
        "flake-public"
        "cluster-data"
      ];
    };
    hardwareModules = [
      ../../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
    overrides = [ ];
  };

  library-1 = {
    exported = true;
    system = "x86_64-linux";
    roles = [
      "workstation"
      "archive-node"
      "radicle-seed"
    ];
    networks = [
      "privateYggdrasil"
      "tailscale"
    ];
    publicYggdrasil = false;
    dendrites = [
      "storage/tape"
      "storage/archive"
      "network/radicle"
    ];
    fruits = [ "tapelib" ];
    users = [ "user1" ];
    facts.storage.tape.devices = {
      changer = "/dev/tape/by-id/REPLACE_ME";
      drive = "/dev/tape/by-id/REPLACE_ME";
      drives = [ "/dev/tape/by-id/REPLACE_ME" ];
    };
    org.storage.tape = {
      manager = "tapelib";
      tapelib = {
        stateDir = "/var/lib/tapelib";
        openFirewall = false;
      };
    };
    org.storage.annex = {
      group = "archive";
      archive.tape.enable = true;
    };
    org.network.radicle = {
      privateKeyFile = "/var/lib/radicle/keys/radicle";
      repos = [ "cluster-data" ];
    };
    hardwareModules = [
      ../../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
    overrides = [ ];
  };
}
