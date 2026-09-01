{
  system = "x86_64-linux";
  hostname = "eVolver";
  profiles = [ ];
  state = "suspended";
  identity = {
    id = "eVolver";
    aliases = [ ];
  };
  hardware.snapshot = {
    format = "arbor/hardware";
    version = 1;
    facts = {
      rootFilesystem = "ext4";
      bootFilesystem = "vfat";
      cpu = "intel";
    };
  };
  metadata.migration = {
    disposition = "identity-only";
    source = "references/flake-devbox/config/hosts.json";
    reason = "Stable legacy workstation identity; generated hardware remains reference evidence only.";
  };
}
