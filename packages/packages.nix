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
    clusterctl = pkgs.callPackage ../tools/clusterctl/clusterctl-package.nix { };
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
    bootstrap-validate = pkgs.writeShellApplication {
      name = "bootstrap-validate";
      runtimeInputs = with pkgs; [
        nix
        python3
      ];
      text = ''
        exec ${pkgs.python3}/bin/python ${../bootstrap/bootstrap-validate.py} "$@"
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
    live-installer = pkgs.writeShellApplication {
      name = "live-installer";
      runtimeInputs = with pkgs; [
        coreutils
        nix
        python3
      ];
      text = ''
        exec ${pkgs.python3}/bin/python ${../bootstrap/live-installer.py} "$@"
      '';
    };
    live-installer-usb = pkgs.writeShellApplication {
      name = "live-installer-usb";
      runtimeInputs = with pkgs; [
        coreutils
        nix
        python3
      ];
      text = ''
        exec ${pkgs.python3}/bin/python ${../bootstrap/live-installer.py} write "$@"
      '';
    };
    nbootstrap = pkgs.writeShellApplication {
      name = "nbootstrap";
      runtimeInputs = with pkgs; [
        coreutils
        gitMinimal
        nix
        openssh
        python3
      ];
      text = ''
        export COPILOT_BOOTSTRAP_SCRIPT_DIR=${../bootstrap}
        exec ${pkgs.python3}/bin/python ${../bootstrap/nbootstrap.py} "$@"
      '';
    };
  }
