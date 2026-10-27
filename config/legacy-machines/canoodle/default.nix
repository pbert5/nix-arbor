{
  system = "x86_64-linux";
  hostname = "canoodle";
  profiles = [ ];
  state = "suspended";
  identity = {
    id = "canoodle";
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
    reason = "Stable legacy laptop identity; host configuration remains outside Nix Arbor.";
  };
}
