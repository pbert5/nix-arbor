{
  config,
  lib,
  ...
}:
let
  eVolver = config.flake.nixosConfigurations.eVolver.config;
  packageNames = map (
    package: package.pname or package.name or ""
  ) eVolver.environment.systemPackages;
  requiredPackageNames = [
    "codex"
    "codex-switch"
    "docker-compose"
    "devcontainer"
    "gh"
    "git"
    "nodejs"
    "rtk"
    "uv"
  ];
in
{
  perSystem =
    { pkgs, ... }:
    let
      src = ../.;
    in
    {
      checks = {
        ci-runner-isolation =
          let
            baseR640 = config.flake.nixosConfigurations."r640-0";
            enabledR640 = baseR640.extendModules {
              modules = [
                (_: {
                  arbor.ci.runners = {
                    enable = true;
                    repositories.meta_bal = {
                      enable = true;
                      forkPRWorkflowsDisabled = true;
                    };
                  };
                })
              ];
            };
            publicRunnerR640 = baseR640.extendModules {
              modules = [
                (_: {
                  arbor.ci.runners = {
                    enable = true;
                    repositories.nix-arbor = {
                      enable = true;
                      forkPRWorkflowsDisabled = true;
                    };
                  };
                })
              ];
            };
            forkableRunnerR640 = baseR640.extendModules {
              modules = [
                (_: {
                  arbor.ci.runners = {
                    enable = true;
                    repositories.meta_bal = {
                      enable = true;
                      forkPRWorkflowsDisabled = false;
                    };
                  };
                })
              ];
            };
            untrustedR640 = baseR640.extendModules {
              modules = [
                (_: {
                  arbor.ci.runners.repositories.meta_bal.trustedEvents = [ "pull_request" ];
                })
              ];
            };
            broadIPv4AllowR640 = baseR640.extendModules {
              modules = [
                (_: {
                  arbor.ci.runners.repositories.meta_bal.allowedNetworks = [ "0.0.0.0/00" ];
                })
              ];
            };
            broadIPv6AllowR640 = baseR640.extendModules {
              modules = [
                (_: {
                  arbor.ci.runners.repositories.meta_bal.allowedNetworks = [ "::/0" ];
                })
              ];
            };
            host = enabledR640.config;
            guest = host.microvm.vms.arbor-ci-meta-bal.config.config;
            dockerVolume = builtins.head guest.microvm.volumes;
            runner = guest.services.github-runners.meta-bal;
          in
          assert !config.flake.nixosConfigurations."r640-0".config.arbor.ci.runners.enable;
          assert
            !config.flake.nixosConfigurations."r640-0".config.arbor.ci.runners.inventory.nix-arbor.forkPRWorkflowsDisabled;
          assert
            config.flake.nixosConfigurations."r640-0".config.arbor.ci.runners.inventory.nix-arbor.repositoryVisibility
            == "public";
          assert !config.flake.nixosConfigurations."r640-0".config.microvm.host.enable;
          assert config.flake.nixosConfigurations."r640-0".config.virtualisation.docker.enable;
          assert host.microvm.host.enable;
          assert host.arbor.ci.runners.inventory.meta_bal.forkPRWorkflowsDisabled;
          assert host.microvm.vms.arbor-ci-meta-bal.autostart;
          assert runner.ephemeral;
          assert runner.count == 1;
          assert runner.url == "https://github.com/pbert5/meta_bal";
          assert
            runner.extraLabels == [
              "r640-0"
              "meta-bal"
            ];
          assert runner.tokenFile == "/run/arbor-ci-secrets/token";
          assert guest.virtualisation.docker.enable;
          assert guest.fileSystems."/var/lib/docker".device == "/dev/disk/by-label/arbor-docker";
          assert builtins.elem "var-lib-docker.mount" guest.systemd.services.docker.requires;
          assert guest.systemd.services.docker.unitConfig.ConditionPathIsMountPoint == "/var/lib/docker";
          assert guest.systemd.services."github-runner-meta-bal".serviceConfig.Restart == "on-success";
          assert (builtins.head guest.microvm.shares).readOnly;
          assert
            (builtins.head guest.microvm.shares).source == "/var/lib/arbor-secrets/github-runners/meta_bal";
          assert (builtins.head guest.microvm.shares).source != "/var/run/docker.sock";
          assert dockerVolume.mountPoint == "/var/lib/docker";
          assert dockerVolume.size == 32768;
          assert host.systemd.services."microvm@arbor-ci-meta-bal".serviceConfig.MemoryMax == "8704M";
          assert host.systemd.services."microvm@arbor-ci-meta-bal".serviceConfig.IPAddressDeny != [ ];
          assert host.systemd.slices.arbor-ci-runners.sliceConfig.MemoryMax == "12288M";
          assert
            !(builtins.tryEval (
              builtins.deepSeq untrustedR640.config.arbor.ci.runners.repositories.meta_bal.trustedEvents true
            )).success;
          assert
            !(builtins.tryEval (builtins.deepSeq broadIPv4AllowR640.config.system.build.toplevel.drvPath true))
            .success;
          assert
            !(builtins.tryEval (builtins.deepSeq broadIPv6AllowR640.config.system.build.toplevel.drvPath true))
            .success;
          assert
            !(builtins.tryEval (builtins.deepSeq publicRunnerR640.config.system.build.toplevel.drvPath true))
            .success;
          assert
            !(builtins.tryEval (builtins.deepSeq forkableRunnerR640.config.system.build.toplevel.drvPath true))
            .success;
          assert
            host.arbor.ci.runners.inventory.meta_bal.labels == [
              "self-hosted"
              "linux"
              "x64"
              "r640-0"
              "meta-bal"
            ];
          pkgs.runCommand "nix-arbor-ci-runner-isolation" { } ''
            touch $out
          '';

        evolver-developer-tools =
          assert lib.all (name: lib.elem name packageNames) requiredPackageNames;
          assert eVolver.virtualisation.docker.enable;
          pkgs.runCommand "nix-arbor-evolver-developer-tools" { } ''
            touch $out
          '';

        nixfmt = pkgs.runCommand "nix-arbor-nixfmt" { } ''
          { find ${src}/config ${src}/modules -type f -name '*.nix' -print0; printf '%s\\0' ${src}/flake.nix; } \
            | xargs -0 ${pkgs.nixfmt}/bin/nixfmt --check
          touch $out
        '';

        statix = pkgs.runCommand "nix-arbor-statix" { } ''
          ${pkgs.statix}/bin/statix check ${../modules}
          touch $out
        '';

        deadnix = pkgs.runCommand "nix-arbor-deadnix" { } ''
          ${pkgs.deadnix}/bin/deadnix --fail ${../flake.nix} ${../modules}
          touch $out
        '';
      };
    };
}
