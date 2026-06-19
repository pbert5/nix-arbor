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
    ];
    fruits = [ ];
    users = [
      "user1"
      "user2"
    ];
    facts = { };
    org.network.membership.optIn = "all";
    org.clusterIdentity = {
      role = "leader";
      registryTransport.identityFile = null;
      services = {
        ssh.enableLiveKnownHosts = true;
        yggdrasil.enableLiveIdentity = true;
      };
    };
    hardwareModules = [
      ../modules/_hardware-configs/public-example-hardware-configuration.nix
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
    hardwareModules = [
      ../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
    overrides = [ ];
  };
}
