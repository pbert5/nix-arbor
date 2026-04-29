{
  workstation = {
    dendrites = [
      "base"
      "dev-tools"
      "system/workstation"
    ];
    fruits = [ ];
    homes = [
      "shared/common"
      "shared/ssh"
      "shared/workstation"
    ];
    users = [ ];
  };

  compute-worker = {
    dendrites = [
      "base"
      "system/compute-worker"
    ];
    fruits = [ ];
    homes = [ "shared/common" ];
    users = [ ];
  };

  # Storage fabric roles.
  # Hosts opt into one or more of these via their roles list in inventory/hosts.nix.

  annex-client = {
    # Workstation or compute node that reads/writes annex content.
    dendrites = [ "storage/git-annex" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  annex-storage = {
    # Stable node that stores annex content and accepts SSH transfers.
    dendrites = [
      "storage/git-annex"
    ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  annex-workstation = {
    # Desktop/laptop that works with annex content locally.
    # Gets the "workstation" preferred-content group.
    dendrites = [ "storage/git-annex" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  annex-compute-cache = {
    # Ephemeral compute node that caches active job inputs.
    # Gets the "compute" preferred-content group.
    dendrites = [ "storage/git-annex" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  seaweed-master = {
    dendrites = [ "storage/seaweedfs-hot" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  seaweed-volume = {
    dendrites = [ "storage/seaweedfs-hot" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  seaweed-filer = {
    dendrites = [ "storage/seaweedfs-hot" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  seaweed-s3 = {
    dendrites = [ "storage/seaweedfs-hot" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  archive-node = {
    # Must define at least one archive backend in org.storage.annex.archive.
    dendrites = [ "storage/archive" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  radicle-seed = {
    # Mirrors flake repo and annex metadata repo over private Ygg.
    dendrites = [ "network/radicle" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };

  storage-fabric-observer = {
    # Adds fabric-status CLI + daily annex fsck timer.
    dendrites = [ "storage/storage-observability" ];
    fruits = [ ];
    homes = [ ];
    users = [ ];
  };
}
