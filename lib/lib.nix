{ inputs, lib }:
let
  endpoints = import ./endpoints.nix { inherit lib; };
  helpers = import ./helpers.nix { inherit lib; };
  inventoryLib = import ./inventory.nix {
    inherit helpers lib;
  };
  identityRequirements = import ./identity-requirements.nix { inherit lib; };
  cheatsheets = import ./cheatsheets.nix { inherit lib; };
  registries = import ./registries.nix { inherit lib; };
  topology = import ./topology.nix { inherit lib; };
  users = import ./users.nix { inherit lib; };
  validation = import ./validation.nix {
    inherit endpoints helpers lib;
  };
  assembly = import ./assembly.nix {
    inherit
      cheatsheets
      helpers
      inputs
      lib
      validation
      ;
    topologyLib = topology;
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
    cheatsheets
    helpers
    identityRequirements
    registries
    topology
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
} # TODO: something about this frustrates me, its literaly just a bunch of import logic, we should have dynamic import behavior to make this completely unnesesary
