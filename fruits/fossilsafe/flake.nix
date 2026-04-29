{
  description = "Feature flake for the local FossilSafe fork";

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
            ltfsOpen = pkgs.callPackage ./nix/ltfs-open.nix { };
            fossilsafe = pkgs.callPackage ./nix/fossilsafe-package.nix {
              inherit ltfsOpen;
              sourceRoot = ./FOSSILSAFE;
            };
          in
          {
            packages = {
              default = fossilsafe;
              inherit fossilsafe ltfsOpen;
            };

            checks = import ./nix/fossilsafe-checks.nix {
              inherit fossilsafe inputs pkgs;
            };

            devShells.default = pkgs.mkShell {
              packages = [
                fossilsafe
                fossilsafe.pythonEnv
                ltfsOpen
                pkgs.fuse3
                pkgs.git
                pkgs.jq
                pkgs.nodejs
                pkgs.pkg-config
                pkgs.python3
                pkgs.ruff
                pkgs.shellcheck
              ];
            };
          };

        flake.nixosModules.fossilsafe = import ./nix/fossilsafe-module.nix;
      }
    );
}
