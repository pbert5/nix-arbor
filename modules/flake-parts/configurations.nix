{
  inputs,
  lib,
  ...
}:
let
  dendriticLib = import ../../lib/lib.nix {
    inherit inputs lib;
  };
  baseInventory = dendriticLib.normalizeInventory (import ../../inventory/inventory.nix { inherit inputs; });
  registries = {
    dendrites = dendriticLib.registries.mkDendriteRegistry ../../dendrites;
    fruits = dendriticLib.registries.mkFruitRegistry ../../fruits;
    homes = dendriticLib.registries.mkHomeRegistry ../../homes;
    hosts = dendriticLib.registries.mkHostRegistry ../../hosts;
  };
  inventory = baseInventory // {
    identityRequirements = dendriticLib.identityRequirements.resolve {
      dendriteRegistry = registries.dendrites;
      inventory = baseInventory;
    };
  };
  genericSiteModule = {
    _module.args.site = inventory;
  };
  overlay = import ../../overlays/overlays.nix;
  validationError = dendriticLib.validateInventory {
    inherit inventory;
  };
in
{
  config = builtins.seq validationError {
    flake = {
      nixosConfigurations = dendriticLib.assembly.mkNixosConfigurations {
        inherit genericSiteModule;
        inherit inventory registries;
      };

      homeConfigurations = dendriticLib.assembly.mkHomeConfigurations {
        inherit genericSiteModule;
        inherit inventory registries;
        inherit overlay;
      };
    };
  };
}
