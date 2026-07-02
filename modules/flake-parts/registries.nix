{
  config,
  inputs,
  lib,
  ...
}:
let
  dendriticLib = import ../../lib/lib.nix {
    inherit inputs lib;
  };

  baseInventory = dendriticLib.normalizeInventory (
    import ../../inventory/inventory.nix { inherit inputs; }
  );
  registries = {
    dendrites = dendriticLib.registries.mkDendriteRegistry ../../dendrites;
    fruits = dendriticLib.registries.mkFruitRegistry ../../fruits;
    homes = dendriticLib.registries.mkHomeRegistry ../../homes;
    hosts = dendriticLib.registries.mkHostRegistry ../../hosts;
  };
  cheatsheets = dendriticLib.cheatsheets.collect { inherit registries; };
  inventory = baseInventory // {
    identityRequirements = dendriticLib.identityRequirements.resolve {
      dendriteRegistry = registries.dendrites;
      inventory = baseInventory;
    };
  };
  publishedUserModules = dendriticLib.users.publishNixosModules {
    homeRegistry = registries.homes;
    users = inventory.users;
  };
in
{
  options.dendritic.inventory = lib.mkOption {
    type = lib.types.raw;
    readOnly = true;
    default = inventory;
    description = "Normalized dendritic inventory used to assemble systems and homes.";
  };

  options.dendritic.registries = lib.mkOption {
    type = lib.types.raw;
    readOnly = true;
    default = registries;
    description = "Passive registries for dendrites, fruits, homes, and hosts.";
  };

  config.flake = {
    dendritic = {
      inherit cheatsheets inventory registries;
      lib = dendriticLib;
    };

    inventory = inventory;

    homeModules = lib.mapAttrs (_: entry: entry.module) registries.homes;
    nixosModules =
      (lib.mapAttrs (_: entry: entry.module) registries.dendrites)
      // (lib.mapAttrs (_: entry: entry.module) registries.fruits)
      // (lib.mapAttrs (_: entry: entry.module) registries.hosts)
      // publishedUserModules;
  };
}
