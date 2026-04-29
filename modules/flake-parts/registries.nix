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

  inventory = dendriticLib.normalizeInventory (import ../../inventory/inventory.nix { inherit inputs; });
  registries = {
    dendrites = dendriticLib.registries.mkDendriteRegistry ../../dendrites;
    fruits = dendriticLib.registries.mkFruitRegistry ../../fruits;
    homes = dendriticLib.registries.mkHomeRegistry ../../homes;
    hosts = dendriticLib.registries.mkHostRegistry ../../hosts;
  };
  publishedUserModules = dendriticLib.users.publishNixosModules {
    homeRegistry = registries.homes;
    roles = inventory.roles;
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
      inherit inventory registries;
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
