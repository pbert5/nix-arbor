{
  name = "network/yggdrasil-private";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [
    "private-yggdrasil-mesh"
    "inventory-driven-overlay"
  ];
  requires = [ "network" ];
  conflicts = [ ];
  cheatsheets.fileRegex = "^cheats/.*\\.cheat$";
  identityRequirements = [
    {
      service = "yggdrasil";
      generator = "yggdrasil";
      sourceLedger = "inventory/identity-services/yggdrasil.nix";
    }
  ];
}
