{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.arbor.ci.runners;
  poolRoot = "/mypool";
  runnerDataRoot = "${poolRoot}/ci-runners";
  secretRoot = "/var/lib/arbor-secrets/github-runners";
  runnerUser = "github-runner";
  runnerGroup = "docker";
  protectedNetworks = [
    "0.0.0.0/8"
    "10.0.0.0/8"
    "100.64.0.0/10"
    "127.0.0.0/8"
    "169.254.0.0/16"
    "172.16.0.0/12"
    "192.0.0.0/24"
    "192.168.0.0/16"
    "198.18.0.0/15"
    "224.0.0.0/4"
    "240.0.0.0/4"
    "::/128"
    "::1/128"
    "fc00::/7"
    "fe80::/10"
    "ff00::/8"
  ];
  repoLabel = name: (lib.replaceStrings [ "_" ] [ "-" ] name);
  vmName = name: "arbor-ci-${repoLabel name}";
  secretDir = name: "${secretRoot}/${name}";
  tokenPath = name: "${secretDir name}/token";
  inventory = lib.mapAttrs (name: runner: {
    inherit (runner)
      repository
      repositoryVisibility
      forkPRWorkflowsDisabled
      runnerName
      trustedEvents
      trustedRefs
      memoryMiB
      vcpu
      diskMiB
      blockedNetworks
      allowedNetworks
      ;
    vm = vmName name;
    labels = [
      "self-hosted"
      "linux"
      "x64"
      "r640-0"
      (repoLabel name)
    ];
    lifecycle = "ephemeral-per-job; one active job; VM is operator-managed";
    tokenFile = runner.tokenFile;
    healthProbe = "systemctl is-active microvm@${vmName name}.service";
  }) cfg.repositories;
  enabledRepositories = lib.filterAttrs (_: runner: runner.enable) cfg.repositories;
  runnerServices = {
    arbor-ci-runner-storage = {
      description = "Prepare isolated CI runner disk storage on mypool";
      wantedBy = [ "multi-user.target" ];
      after = [
        "zfs-import-mypool.service"
        "zfs-mount.service"
      ];
      requires = [
        "zfs-import-mypool.service"
        "zfs-mount.service"
      ];
      serviceConfig.Type = "oneshot";
      script = ''
        set -eu
        ${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}
        ${pkgs.coreutils}/bin/install -d -o microvm -g microvm -m 0700 ${runnerDataRoot}
      '';
    };
    "microvm@" = {
      serviceConfig.Slice = "arbor-ci-runners.slice";
      requires = [ "arbor-ci-runner-storage.service" ];
      after = [ "arbor-ci-runner-storage.service" ];
    };
  }
  // lib.listToAttrs (
    map (name: {
      name = "microvm@${vmName name}";
      value.serviceConfig = {
        IPAddressDeny = protectedNetworks ++ cfg.repositories.${name}.blockedNetworks;
        IPAddressAllow = cfg.repositories.${name}.allowedNetworks;
        MemoryMax = "${toString (cfg.repositories.${name}.memoryMiB + 512)}M";
        CPUQuota = "${toString (cfg.repositories.${name}.vcpu * 100)}%";
      };
    }) (builtins.attrNames enabledRepositories)
  );
  vms = lib.mapAttrs' (name: runner: {
    name = vmName name;
    value = {
      autostart = runner.autostart;
      restartIfChanged = true;
      config = {
        networking.hostName = vmName name;
        networking.useDHCP = true;
        networking.firewall.enable = true;
        system.stateVersion = "26.05";

        microvm = {
          hypervisor = "qemu";
          vcpu = runner.vcpu;
          mem = runner.memoryMiB;
          interfaces = [
            {
              type = "user";
              id = "eth0";
              mac = "02:00:00:00:00:01";
            }
          ];
          shares = [
            {
              source = builtins.dirOf runner.tokenFile;
              mountPoint = "/run/arbor-ci-secrets";
              tag = "ci-secrets";
              proto = "9p";
              securityModel = "none";
              readOnly = true;
            }
          ];
          volumes = [
            {
              image = "${runnerDataRoot}/${vmName name}-docker.img";
              mountPoint = "/var/lib/docker";
              label = "arbor-docker";
              size = runner.diskMiB;
              fsType = "ext4";
            }
          ];
          preStart = ''
            ${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}
            test -d ${runnerDataRoot}
            test -r ${tokenPath name}
          '';
        };

        users.users.${runnerUser} = {
          isSystemUser = true;
          group = runnerGroup;
          extraGroups = [ "docker" ];
          home = "/var/lib/github-runner";
          createHome = true;
        };
        virtualisation.docker.enable = true;
        virtualisation.docker.daemon.settings."data-root" = "/var/lib/docker";
        systemd.services.docker = {
          requires = [ "var-lib-docker.mount" ];
          after = [ "var-lib-docker.mount" ];
          unitConfig.ConditionPathIsMountPoint = "/var/lib/docker";
        };
        services.github-runners.${repoLabel name} = {
          enable = true;
          url = "https://github.com/${runner.repository}";
          name = runner.runnerName;
          count = 1;
          extraLabels = [
            "r640-0"
            (repoLabel name)
          ];
          tokenFile = "/run/arbor-ci-secrets/${builtins.baseNameOf runner.tokenFile}";
          ephemeral = true;
          user = runnerUser;
          group = runnerGroup;
          extraPackages = with pkgs; [
            curl
            docker-client
            git
            jq
            nodejs
          ];
          serviceOverrides = {
            PrivateUsers = false;
            SupplementaryGroups = [ "docker" ];
          };
        };

      };
    };
  }) enabledRepositories;
in
{
  options.arbor.ci.runners = {
    enable = lib.mkEnableOption "isolated repository-scoped CI MicroVM runners";
    maxActiveRunners = lib.mkOption {
      type = lib.types.ints.positive;
      default = 1;
      description = "Maximum number of configured active runner VMs for this host";
    };
    memoryBudgetMiB = lib.mkOption {
      type = lib.types.ints.positive;
      default = 12288;
      description = "Aggregate systemd memory limit for all CI runner VMs";
    };
    cpuBudgetPercent = lib.mkOption {
      type = lib.types.ints.positive;
      default = 600;
      description = "Aggregate systemd CPU quota for all CI runner VMs";
    };
    repositories = lib.mkOption {
      default = { };
      description = "Explicit private-repository runner inventory; no wildcard enrollment is supported.";
      type = lib.types.attrsOf (
        lib.types.submodule (
          { name, ... }: {
            options = {
              enable = lib.mkEnableOption "this repository runner";
              repository = lib.mkOption {
                type = lib.types.strMatching "[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+";
                default = name;
                description = "Exact GitHub owner/repository identity.";
              };
              repositoryVisibility = lib.mkOption {
                type = lib.types.enum [
                  "private"
                  "public"
                ];
                default = "public";
                description = "Verified GitHub visibility; public repositories cannot use this repo-scoped runner.";
              };
              forkPRWorkflowsDisabled = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Set true only after GitHub reports run_workflows_from_fork_pull_requests=false.";
              };
              runnerName = lib.mkOption {
                type = lib.types.str;
                default = "r640-0-${repoLabel name}";
              };
              tokenFile = lib.mkOption {
                type = lib.types.str;
                default = tokenPath name;
                description = "Runtime-only repository credential path; never a Nix store path.";
              };
              autostart = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Start this MicroVM with microvms.target after explicit enablement.";
              };
              trustedEvents = lib.mkOption {
                type = lib.types.listOf (
                  lib.types.enum [
                    "push"
                    "release"
                    "workflow_dispatch"
                  ]
                );
                default = [
                  "push"
                  "workflow_dispatch"
                ];
                description = "Event allowlist that consumer workflows must enforce before selecting this runner.";
              };
              trustedRefs = lib.mkOption {
                type = lib.types.nonEmptyListOf lib.types.str;
                default = [ "refs/heads/main" ];
                description = "Exact refs or documented tag patterns allowed by consumer workflow policy.";
              };
              memoryMiB = lib.mkOption {
                type = lib.types.ints.between 2048 12288;
                default = 8192;
              };
              vcpu = lib.mkOption {
                type = lib.types.ints.between 1 8;
                default = 4;
              };
              diskMiB = lib.mkOption {
                type = lib.types.ints.between 8192 65536;
                default = 32768;
              };
              blockedNetworks = lib.mkOption {
                type = lib.types.listOf (lib.types.strMatching "[0-9A-Fa-f:.]+/[0-9]+");
                default = [ ];
                description = "Additional host or private network CIDRs that this guest must not reach.";
              };
              allowedNetworks = lib.mkOption {
                type = lib.types.listOf (lib.types.strMatching "[0-9A-Fa-f:.]+/[0-9]+");
                default = [ ];
                description = "Narrow CIDRs permitted for approved private services such as the authenticated OCI registry.";
              };
            };
          }
        )
      );
    };
    inventory = lib.mkOption {
      type = lib.types.attrs;
      readOnly = true;
      description = "Evaluated runner contracts consumed by downstream workstreams.";
    };
  };

  config = lib.mkMerge [
    {
      arbor.ci.runners.inventory = inventory;
      microvm.host.enable = cfg.enable;
      microvm.stateDir = "/var/lib/microvms";
      microvm.vms = lib.mkIf cfg.enable vms;
      assertions = [
        {
          assertion =
            !cfg.enable || builtins.length (builtins.attrNames enabledRepositories) <= cfg.maxActiveRunners;
          message = "Configured CI runner count exceeds arbor.ci.runners.maxActiveRunners";
        }
        {
          assertion = lib.all (name: builtins.match "[A-Za-z0-9][A-Za-z0-9_.-]*" name != null) (
            builtins.attrNames cfg.repositories
          );
          message = "CI runner repository keys must be simple names without path separators";
        }
        {
          assertion =
            builtins.length (lib.unique (map repoLabel (builtins.attrNames cfg.repositories)))
            == builtins.length (builtins.attrNames cfg.repositories);
          message = "CI runner repository keys must not normalize to duplicate runner labels";
        }
        {
          assertion = lib.all (name: cfg.repositories.${name}.tokenFile == tokenPath name) (
            builtins.attrNames cfg.repositories
          );
          message = "CI runner credentials must use the exact repository-specific runtime token path";
        }
        {
          assertion = lib.all (runner: !(lib.hasPrefix "/nix/store/" runner.tokenFile)) (
            lib.attrValues cfg.repositories
          );
          message = "CI runner credentials must never be placed in the Nix store";
        }
        {
          assertion = lib.all (
            runner: lib.all (network: builtins.match ".*/0+" network == null) runner.allowedNetworks
          ) (lib.attrValues cfg.repositories);
          message = "CI runner allowedNetworks must not grant a default route";
        }
        {
          assertion =
            !cfg.enable
            || lib.all (runner: runner.repositoryVisibility == "private" && runner.forkPRWorkflowsDisabled) (
              lib.attrValues enabledRepositories
            );
          message = "CI runner enrollment requires a private repository with fork pull-request workflows disabled";
        }
        {
          assertion =
            !cfg.enable
            ||
              lib.foldl' (total: runner: total + runner.memoryMiB + 512) 0 (lib.attrValues enabledRepositories)
              <= cfg.memoryBudgetMiB;
          message = "Enabled CI runner guests exceed the aggregate memory budget including hypervisor overhead";
        }
        {
          assertion =
            !cfg.enable
            ||
              lib.foldl' (total: runner: total + runner.vcpu * 100) 0 (lib.attrValues enabledRepositories)
              <= cfg.cpuBudgetPercent;
          message = "Enabled CI runner guests exceed the aggregate CPU quota";
        }
      ];
      systemd.tmpfiles.rules = lib.optionals cfg.enable (
        [ "d ${secretRoot} 0710 root microvm - -" ]
        ++ map (name: "d ${secretDir name} 0710 root microvm - -") (builtins.attrNames cfg.repositories)
      );
      systemd.tmpfiles.settings."10-microvm" = lib.mkIf cfg.enable (
        lib.listToAttrs (
          map (name: {
            name = secretDir name;
            value.d = {
              user = lib.mkForce "root";
              group = lib.mkForce "microvm";
              mode = lib.mkForce "0710";
            };
          }) (builtins.attrNames cfg.repositories)
        )
      );
      systemd.services = lib.mkIf cfg.enable runnerServices;
      systemd.slices.arbor-ci-runners = lib.mkIf cfg.enable {
        description = "Aggregate resource limits for isolated CI runner guests";
        sliceConfig = {
          MemoryMax = "${toString cfg.memoryBudgetMiB}M";
          CPUQuota = "${toString cfg.cpuBudgetPercent}%";
        };
      };
    }
    (lib.mkIf cfg.enable {
      microvm.autostart = lib.mapAttrsToList (name: _: vmName name) (
        lib.filterAttrs (_: runner: runner.autostart) enabledRepositories
      );
    })
  ];
}
