{
  description = "Feature flake for the tapelib tape-library overlay scaffold";

  inputs = {
    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };

    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };

  outputs = inputs:
    inputs.flake-parts.lib.mkFlake { inherit inputs; } (
      { ... }:
      {
        systems = [
          "x86_64-linux"
          "aarch64-linux"
        ];

        perSystem =
          { pkgs, ... }:
          let
            tapelib = pkgs.callPackage ./nix/tapelib-package.nix {
              sourceRoot = ./.;
            };
          in
          {
            packages = {
              default = tapelib;
              inherit tapelib;
            };

            devShells.default = pkgs.mkShell {
              packages = [
                pkgs.fuse3
                pkgs.git
                pkgs.jq
                pkgs.lsof
                pkgs.mtx
                pkgs.python3
                pkgs.python3Packages.fusepy
                pkgs.python3Packages.pytest
                pkgs.sg3_utils
                pkgs.sqlite
                tapelib
              ];
            };
          };

        flake.nixosModules.tapelib = import ./nix/tapelib-module.nix;
      }
    );
}
