{
  system = "x86_64-linux";
  hostname = "eVolver";
  profiles = [
    "desktop"
    "arborParticipant"
  ];
  hardware.snapshot = {
    format = "arbor/hardware";
    version = 1;
    facts = {
      bootMode = "uefi";
      bootFilesystem = "vfat";
      cpu = "intel-xeon-w-2123";
      product = "HP Z4 G4 Workstation";
      rootFilesystem = "ext4";
      rootStorage = "CT1000BX500SSD1";
    };
  };
  metadata.migration = {
    source = "references/flake-devbox/config/hosts.json";
    disposition = "migrated-machine";
  };
}
