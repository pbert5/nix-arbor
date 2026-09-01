{
  system = "x86_64-linux";
  hostname = "t320-0";
  profiles = [ ];
  state = "suspended";
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
      dataPools = [
        "big"
        "fast"
      ];
    };
  };
  metadata.migration = {
    disposition = "identity-only";
    source = "references/flake-devbox/config/hosts.json";
    reason = "Stable legacy storage host identity; tape, ZFS, and media services require a separately reviewed component.";
  };
}
