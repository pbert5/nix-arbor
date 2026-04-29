{ pkgs ? null }:
if pkgs == null then
  { }
else
  let
    ltfsOpen = pkgs.callPackage ../fruits/fossilsafe/nix/ltfs-open.nix { };
  in
  {
    fossilsafe = pkgs.callPackage ../fruits/fossilsafe/nix/fossilsafe-package.nix {
      inherit ltfsOpen;
      sourceRoot = ../fruits/fossilsafe/FOSSILSAFE;
    };
    "ltfs-open" = ltfsOpen;
    public-export = pkgs.writeShellApplication {
      name = "public-export";
      runtimeInputs = with pkgs; [
        nix
        python3
      ];
      text = ''
        export PUBLIC_EXPORT_CONFIG=${../public-export/export-config.json}
        export PUBLIC_EXPORT_OVERLAY=${../public-export/overlay}
        exec ${pkgs.python3}/bin/python ${../bootstrap/public-export.py} "$@"
      '';
    };
    yggdrasil-bootstrap = pkgs.writeShellApplication {
      name = "yggdrasil-bootstrap";
      runtimeInputs = with pkgs; [
        gitMinimal
        nix
        openssh
        python3
      ];
      text = ''
        exec ${pkgs.python3}/bin/python ${../bootstrap/yggdrasil-bootstrap.py} "$@"
      '';
    };
  }
