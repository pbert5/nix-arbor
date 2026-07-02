{
  config,
  inputs,
  lib,
  ...
}:
let
  dendriticLib = import ../../lib/lib.nix { inherit inputs lib; };
in
{
  imports = [ inputs.nix-topology.flakeModule ];

  perSystem = {
    topology.modules = [
      {
        networks = dendriticLib.topology.mkGlobalNetworks {
          inventory = config.dendritic.inventory;
        };
      }
    ];
  };
}
