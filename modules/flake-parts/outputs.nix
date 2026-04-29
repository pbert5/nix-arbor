{
  config,
  inputs,
  lib,
  ...
}:
let
  overlay = import ../../overlays/overlays.nix;
  unstableOverlay = final: _prev: {
    unstable = import inputs.nixpkgs-unstable {
      inherit (final.stdenv.hostPlatform) system;
      config.allowUnfree = true;
    };
  };
in
{
  imports = [
    inputs.home-manager.flakeModules.home-manager
  ];

  systems = lib.unique (builtins.map (host: host.system) (builtins.attrValues config.dendritic.inventory.hosts));

  perSystem =
    { system, ... }:
    let
      pkgs = import inputs.nixpkgs {
        inherit system;
        config.allowUnfree = true;
        overlays = [
          overlay
          unstableOverlay
        ];
      };
      repoPackages = import ../../packages/packages.nix { inherit pkgs; };
    in
    {
      _module.args.pkgs = pkgs;
      packages =
        repoPackages
        // {
          bootstrap-host = repoPackages.yggdrasil-bootstrap;
          colmena = inputs.colmena.packages.${system}.colmena;
          deploy-rs = inputs.deploy-rs.packages.${system}.deploy-rs;
        };
      apps.public-export = {
        type = "app";
        program = "${repoPackages.public-export}/bin/public-export";
        meta.description = "Export a sanitized public mirror from an allowlisted subset of this repo";
      };
      apps.yggdrasil-bootstrap = {
        type = "app";
        program = "${repoPackages.yggdrasil-bootstrap}/bin/yggdrasil-bootstrap";
        meta.description = "Bootstrap or refresh a host-generated Yggdrasil identity into inventory";
      };
      apps.bootstrap-host = {
        type = "app";
        program = "${repoPackages.yggdrasil-bootstrap}/bin/yggdrasil-bootstrap";
        meta.description = "Operator-facing alias for the host bootstrap workflow";
      };
      apps.colmena = {
        type = "app";
        program = "${inputs.colmena.packages.${system}.colmena}/bin/colmena";
        meta.description = "Run the flake-pinned Colmena deployment tool";
      };
      apps.deploy-rs = {
        type = "app";
        program = "${inputs.deploy-rs.packages.${system}.deploy-rs}/bin/deploy";
        meta.description = "Run the flake-pinned deploy-rs deployment tool";
      };
    };

  flake = {
    overlays.default = overlay;
  };
}
