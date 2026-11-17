{ inputs, ... }:
{
  # Export child component modules from one neutral composition boundary.
  config.flake = {
    homeModules = {
      ashzsh = { ... }: {
        imports = [
          inputs.ashzsh.homeModules.default
          ./fastfetch-arbor.nix
        ];
      };
      tilingDesktop = inputs.tilingDesktop.homeModules.default;
    };
    nixosModules = {
      tilingDesktop = inputs.tilingDesktop.nixosModules.default;
      arborRegistry = inputs.arbor-registry.nixosModules.default;
      arborNetworkManager = inputs.arbor-network-manager.nixosModules.default;
      yggdrasilPrivate = inputs.yggdrasil-private.nixosModules.default;
      arborVaultRuntime = inputs.arbor-registry.nixosModules.vault-runtime;
      arborVaultRuntimeUpstream = inputs.arbor-registry.nixosModules.vault-runtime-upstream;
    };
  };
}
