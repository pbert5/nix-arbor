{
  description = "Insurance snapshot experiment for mirroring flake inputs, sources, and optional build closures";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };

  outputs =
    { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      insurance = pkgs.writeShellApplication {
        name = "flake-insurance";
        runtimeInputs = [
          pkgs.coreutils
          pkgs.git
          pkgs.nix
          pkgs.python3
          pkgs.rsync
        ];
        text = ''
          exec ${pkgs.python3}/bin/python ${./insurance.py} "$@"
        '';
      };
      mkApp = program: {
        type = "app";
        inherit program;
      };
    in
    {
      packages.${system} = {
        default = insurance;
        insurance = insurance;
      };

      apps.${system} = {
        default = mkApp "${insurance}/bin/flake-insurance";
        insurance = mkApp "${insurance}/bin/flake-insurance";
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = [
          pkgs.git
          pkgs.nix
          pkgs.python3
          pkgs.rsync
        ];
      };

      formatter.${system} = pkgs.nixfmt-rfc-style;
    };
}
