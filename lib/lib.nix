{ inputs, lib }:
let
  endpoints = import ./endpoints.nix { inherit lib; };
  helpers = import ./helpers.nix { inherit lib; };
  inventoryLib = import ./inventory.nix {
    inherit helpers lib;
  };
  registries = import ./registries.nix { inherit lib; };
  users = import ./users.nix { inherit lib; };
  validation = import ./validation.nix {
    inherit endpoints helpers lib;
  };
  assembly = import ./assembly.nix {
    inherit helpers inputs lib validation;
    usersLib = users;
  };
  deployments = import ./deployments.nix {
    inherit assembly inputs lib;
  };
in
{
  inherit
    deployments
    endpoints
    helpers
    registries
    users
    ;

  mkFruit = assembly.mkFruit;
  mkHome = assembly.mkHome;
  mkHost = assembly.mkHost;
  mkHostDefinition = assembly.mkHostDefinition;
  normalizeInventory = inventoryLib.normalizeInventory;
  resolveDendrites = assembly.resolveDendrites;
  resolveFruits = assembly.resolveFruits;
  validateComposition = validation.assertComposition;
  validateInventory = validation.assertInventory;

  assembly = assembly;
  validation = validation;
}#TODO: something about this frustrates me, its literaly just a bunch of import logic, we should have dynamic import behavior to make this completely unnesesary
