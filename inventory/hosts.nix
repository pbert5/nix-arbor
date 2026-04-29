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
    dendrites = [ "desktop/gnome" ];
    fruits = [ ];
    users = [
      "user1"
      "user2"
    ];
    facts = { };
    org = { };
    hardwareModules = [
      ../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
    overrides = [ ];
  };

  storage-1 = {
    exported = true;
    system = "x86_64-linux";
    roles = [ "workstation" ];
    networks = [
      "privateYggdrasil"
      "tailscale"
    ];
    publicYggdrasil = false;
    dendrites = [ "storage/zfs" ];
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
    hardwareModules = [
      ../modules/_hardware-configs/public-example-hardware-configuration.nix
    ];
    overrides = [ ];
  };
}
