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

  inventory = config.dendritic.inventory;
  registries = config.dendritic.registries;
  genericSiteModule = {
    _module.args.site = inventory;
  };

  colmena = dendriticLib.deployments.mkColmena {
    inherit genericSiteModule inventory registries;
  };

  deploy = dendriticLib.deployments.mkDeployRs {
    inherit inventory;
    nixosConfigurations = config.flake.nixosConfigurations;
  };
in
{
  config.flake = {
    inherit colmena deploy;
    colmenaHive = inputs.colmena.lib.makeHive colmena;
  };
}