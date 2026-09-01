{
  system = "x86_64-linux";
  hostname = "t320-0";
  profiles = [
    "server"
    "arborParticipant"
  ];
  identity = {
    id = "t320-0";
    aliases = [ ];
  };
  hardware.snapshot = {
    format = "arbor/hardware";
    version = 1;
    facts = {
      chassis = "Dell PowerEdge T320";
      cpu = "Intel Xeon E5-2470 v2";
      rootFilesystem = "ext4";
      rootDevice = "/dev/disk/by-label/nixos-root";
      bootDevice = "/dev/disk/by-label/NIXBOOT";
      dataPools = [
        "big"
        "fast"
      ];
    };
  };
  metadata.migration = {
    disposition = "migrated-machine";
    source = "references/flake-devbox/config/hosts.json";
    reason = "Minimal physical-host definition: EFI boot, labeled root filesystems, LAN bridge, public SSH access, and Arbor participant runtime. Legacy storage and media workloads remain unselected.";
  };
}
