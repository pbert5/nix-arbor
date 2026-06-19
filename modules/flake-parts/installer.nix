{
  inputs,
  lib,
  ...
}:
{
  perSystem =
    { system, ... }:
    let
      installerConfiguration =
        if system != "x86_64-linux" then
          null
        else
          inputs.nixpkgs.lib.nixosSystem {
            inherit system;
            modules = [
              ../../bootstrap/live-installer.nix
            ];
          };
    in
    {
      packages = lib.optionalAttrs (installerConfiguration != null) {
        live-installer-iso = installerConfiguration.config.system.build.isoImage;
      };
    };
}
