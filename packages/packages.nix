{
  pkgs ? null,
}:
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
    codex-switch = pkgs.codex-switch;
    hydrui-server =
      pkgs.callPackage ../dendrites/desktop/dendrites/hydrus/dendrites/hydrui/_packages/hydrui-server.nix
        { };
    "host-vm" = pkgs.writeShellApplication {
      name = "host-vm";
      runtimeInputs = with pkgs; [
        coreutils
        nix
      ];
      text = ''
        set -euo pipefail

        usage() {
          cat <<'EOF'
        Usage: host-vm [--flake PATH] [--state-dir PATH] [--fresh] [--ssh-port PORT] HOST

        Build and launch a host's interactive NixOS VM from this flake.
        EOF
        }

        flake_root=$PWD
        state_dir=
        fresh=0
        ssh_port=
        host=

        while [ $# -gt 0 ]; do
          case "$1" in
            --flake)
              [ $# -ge 2 ] || { echo "--flake requires a path" >&2; exit 2; }
              flake_root=$2
              shift 2
              ;;
            --state-dir)
              [ $# -ge 2 ] || { echo "--state-dir requires a path" >&2; exit 2; }
              state_dir=$2
              shift 2
              ;;
            --fresh)
              fresh=1
              shift
              ;;
            --ssh-port)
              [ $# -ge 2 ] || { echo "--ssh-port requires a port" >&2; exit 2; }
              ssh_port=$2
              shift 2
              ;;
            -h|--help)
              usage
              exit 0
              ;;
            --)
              shift
              break
              ;;
            -*)
              echo "Unknown option: $1" >&2
              usage >&2
              exit 2
              ;;
            *)
              host=$1
              shift
              break
              ;;
          esac
        done

        if [ -z "$host" ]; then
          echo "HOST is required" >&2
          usage >&2
          exit 2
        fi

        if [ $# -gt 0 ]; then
          echo "Unexpected extra arguments: $*" >&2
          usage >&2
          exit 2
        fi

        flake_root=$(realpath "$flake_root")
        state_dir=''${state_dir:-"$flake_root/.vm-state/$host"}
        mkdir -p "$state_dir"

        result_link="$state_dir/result"
        rm -f "$result_link"

        echo "Building VM for $host from $flake_root"
        nix build --out-link "$result_link" "$flake_root#nixosConfigurations.$host.config.system.build.vm"

        runner=
        for candidate in \
          "$result_link/bin/run-$host-vm" \
          "$result_link/bin/run-nixos-vm" \
          "$result_link"/bin/run-*-vm
        do
          if [ -x "$candidate" ]; then
            runner=$candidate
            break
          fi
        done

        if [ -z "$runner" ]; then
          echo "Unable to find a VM runner under $result_link/bin" >&2
          exit 1
        fi

        if [ "$fresh" -eq 1 ]; then
          rm -f "$state_dir/$host.qcow2"
        fi

        echo "VM state dir: $state_dir"
        echo "If the host defines a VM test password, the default login is usually ash / ash."
        if [ -n "$ssh_port" ]; then
          export QEMU_NET_OPTS="''${QEMU_NET_OPTS:+$QEMU_NET_OPTS,}hostfwd=tcp:127.0.0.1:$ssh_port-:22"
          echo "Forwarding host TCP $ssh_port to guest port 22"
        fi

        cd "$state_dir"
        exec "$runner"
      '';
    };
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
