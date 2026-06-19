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
          agenix = inputs.agenix.packages.${system}.default;
          bootstrap-host = repoPackages.yggdrasil-bootstrap;
          colmena = inputs.colmena.packages.${system}.colmena;
          deploy-rs = inputs.deploy-rs.packages.${system}.deploy-rs;
          sops = pkgs.sops;
        };
      apps.agenix = {
        type = "app";
        program = "${inputs.agenix.packages.${system}.default}/bin/agenix";
        meta.description = "Run the flake-pinned agenix CLI for encrypted secret editing and rekeying";
      };
      apps.sops = {
        type = "app";
        program = "${pkgs.sops}/bin/sops";
        meta.description = "Run the flake-pinned SOPS CLI for encrypted identity ledgers";
      };
      apps.bootstrap-validate = {
        type = "app";
        program = "${repoPackages.bootstrap-validate}/bin/bootstrap-validate";
        meta.description = "Validate bootstrap inventory, leader root access, and generated deploy targets";
      };
      apps.clusterctl = {
        type = "app";
        program = "${repoPackages.clusterctl}/bin/clusterctl";
        meta.description = "Manage the live signed cluster identity registry";
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
      apps.nbootstrap = {
        type = "app";
        program = "${repoPackages.nbootstrap}/bin/nbootstrap";
        meta.description = "Unified bootstrap CLI for live installer and host enrollment workflows";
      };
      apps.bootstrap-host = {
        type = "app";
        program = "${repoPackages.yggdrasil-bootstrap}/bin/yggdrasil-bootstrap";
        meta.description = "Operator-facing alias for the host bootstrap workflow";
      };
      apps.live-installer = {
        type = "app";
        program = "${repoPackages.live-installer}/bin/live-installer";
        meta.description = "Build the SSH-enabled live installer image from the dedicated bootstrap tool";
      };
      apps.live-installer-usb = {
        type = "app";
        program = "${repoPackages.live-installer-usb}/bin/live-installer-usb";
        meta.description = "Build and write the SSH-enabled live installer image to a USB device";
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
      apps.organizr-test = {
        type = "app";
        program =
          let
            script = pkgs.writeShellScriptBin "organizr-test" ''
              set -euo pipefail
              PORT=19983
              STATE=$(mktemp -d /tmp/organizr-test-XXXXXX)
              cleanup() {
                set +e
                echo
                echo "Stopping..."
                ${pkgs.podman}/bin/podman stop organizr-test 2>/dev/null || true
                ${pkgs.podman}/bin/podman rm -f organizr-test 2>/dev/null || true
                ${pkgs.podman}/bin/podman unshare rm -rf "$STATE" 2>/dev/null || rm -rf "$STATE"
              }
              trap cleanup EXIT
              trap 'trap - EXIT INT TERM; cleanup; exit 130' INT
              trap 'trap - EXIT INT TERM; cleanup; exit 143' TERM

              ${pkgs.podman}/bin/podman rm -f organizr-test >/dev/null 2>&1 || true
              echo "Starting Organizr on http://localhost:$PORT (state: $STATE)"
              echo "On first run this clones the Organizr repo; expect about 60 seconds before the UI is ready."
              ${pkgs.podman}/bin/podman run --rm --name organizr-test \
                -p "127.0.0.1:$PORT:80" \
                -v "$STATE:/config:Z" \
                -e PUID="$(${pkgs.coreutils}/bin/id -u)" \
                -e PGID="$(${pkgs.coreutils}/bin/id -g)" \
                -e TZ=UTC \
                ghcr.io/organizr/organizr:latest &
              echo "Waiting for Organizr to respond..."
              for i in $(seq 1 60); do
                if ${pkgs.curl}/bin/curl -sf http://localhost:$PORT/ >/dev/null 2>&1; then
                  echo "Ready -> http://localhost:$PORT/"
                  wait
                  exit 0
                fi
                sleep 3
              done
              echo "Timed out waiting for Organizr" >&2
              exit 1
            '';
          in
          "${script}/bin/organizr-test";
        meta.description = "Run a throwaway local Organizr instance for testing (port 19983)";
      };
    };

  flake = {
    overlays.default = overlay;
  };
}
