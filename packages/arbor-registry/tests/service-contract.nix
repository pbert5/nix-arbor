{ pkgs, module }:
let
  evaluated = pkgs.lib.evalModules {
    modules = [
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
assert evaluated.config.systemd.timers.arbor-runtime-status.timerConfig.OnUnitActiveSec == "30s";
pkgs.runCommand "arbor-registry-service-contract" { } "touch $out"
