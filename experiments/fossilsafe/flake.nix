{
  description = "Detached FossilSafe experiment runner driven from host inventory";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };

  outputs =
    { nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
      ltfsOpen = pkgs.callPackage ../../fruits/fossilsafe/nix/ltfs-open.nix { };
      fossilsafe = pkgs.callPackage ../../fruits/fossilsafe/nix/fossilsafe-package.nix {
        inherit ltfsOpen;
        sourceRoot = ../../fruits/fossilsafe/FOSSILSAFE;
      };
      fossilsafeLab = pkgs.writeShellApplication {
        name = "fossilsafe-lab";
        runtimeInputs = [
          fossilsafe
          pkgs.nix
          pkgs.python3
        ];
        text = ''
          exec ${pkgs.python3}/bin/python ${./fossilsafe_lab.py} \
            --fossilsafe-bin ${fossilsafe}/bin/fossilsafe \
            --bootstrap-bin ${fossilsafe}/bin/fossilsafe-bootstrap \
            "$@"
        '';
      };
      mkApp = program: {
        type = "app";
        inherit program;
      };
    in
    {
      packages.${system} = {
        default = fossilsafeLab;
        fossilsafe-lab = fossilsafeLab;
        inherit fossilsafe ltfsOpen;
      };

      apps.${system} = {
        default = mkApp "${fossilsafeLab}/bin/fossilsafe-lab";
        run = mkApp "${fossilsafeLab}/bin/fossilsafe-lab";
      };

      devShells.${system}.default = pkgs.mkShell {
        packages = [
          fossilsafe
          ltfsOpen
          pkgs.nix
          pkgs.python3
        ];
      };

      formatter.${system} = pkgs.nixfmt-rfc-style;
    };
}
