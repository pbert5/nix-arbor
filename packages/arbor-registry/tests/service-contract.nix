{ pkgs, module }:
let
  evaluated = pkgs.lib.evalModules {
    specialArgs = { inherit pkgs; };
    modules = [
      {
        # evalModules does not provide the NixOS assertion option; the service
        # contract module uses it to validate its safe runtime paths.
        options.assertions = pkgs.lib.mkOption {
          type = pkgs.lib.types.listOf pkgs.lib.types.anything;
          default = [ ];
        };
        options.systemd = pkgs.lib.mkOption {
          type = pkgs.lib.types.attrsOf pkgs.lib.types.anything;
          default = { };
        };
      }
      module
      {
        cluster.registry.runtime = {
          enable = true;
          openbaoCommand = "/run/current-system/sw/bin/bao";
          providerServices = [ "arbor-vault-runtime-api.service" ];
        };
      }
    ];
  };
  target = evaluated.config.systemd.targets.arbor-participant;
  status = evaluated.config.systemd.services.arbor-runtime-status;
in
assert target.wantedBy == [ "multi-user.target" ];
assert builtins.elem "arbor-registry.service" target.wants;
assert builtins.elem "arbor-registry-transport.service" target.wants;
assert builtins.elem "systemd-vaultd.service" target.wants;
assert builtins.elem "arbor-vault-runtime-api.service" target.wants;
assert status.serviceConfig.Type == "oneshot";
assert status.serviceConfig.RuntimeDirectory == "arbor";
assert status.serviceConfig.RuntimeDirectoryPreserve;
assert evaluated.config.cluster.registry.runtime.registryReadyCommand == "";
assert evaluated.config.systemd.timers.arbor-runtime-status.timerConfig.OnUnitActiveSec == "30s";
pkgs.runCommand "arbor-registry-service-contract" { } "touch $out"
