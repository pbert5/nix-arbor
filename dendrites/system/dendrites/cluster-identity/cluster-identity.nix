{
  config,
  hostInventory,
  lib,
  pkgs,
  site,
  ...
}:
let
  cfg = config.my.clusterIdentity;
  json = pkgs.formats.json { };
  clusterctlPackage = pkgs.callPackage ../../../../tools/clusterctl/clusterctl-package.nix { };
  hostClusterIdentity = lib.attrByPath [ "org" "clusterIdentity" ] { } hostInventory;
  inventoryPolicy = site.identityPolicy or { };
  inventoryIdentities = site.identities or { };
  identityEncryption = inventoryIdentities.encryption or { };
  hostAgeEncryption = identityEncryption.hostAge or { };
  registryPolicy = inventoryPolicy.registry or { };
  leaderPolicy = inventoryPolicy.leaders or { };
  bootstrapInventory = site.hostBootstrap or { };
  privateYggNodes = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" ] { } site;
  sshHostServices = lib.attrByPath [ "ssh-host" ] { } identityServices;
  yggServices = lib.attrByPath [ "yggdrasil" ] { } identityServices;
  serviceFlags = hostClusterIdentity.services or { };
  sshLiveKnownHosts = lib.attrByPath [ "ssh" "enableLiveKnownHosts" ] false serviceFlags;
  hostName = config.networking.hostName;
  identityServices = inventoryIdentities.services or { };
  registryKnownHostsFile = "/etc/cluster-identity/registry-known-hosts";
  defaultRegistryTransportIdentityFile =
    let
      hostRegistryTransportIdentityFile = lib.attrByPath [
        "registryTransport"
        "identityFile"
      ] null hostClusterIdentity;
      bootstrapIdentityFile = lib.attrByPath [ hostName "identityFile" ] null bootstrapInventory;
    in
    if hostRegistryTransportIdentityFile != null then
      hostRegistryTransportIdentityFile
    else
      bootstrapIdentityFile;
  registryTransportIdentityFile = cfg.registryTransportIdentityFile;
  registryKnownHostsText =
    let
      hostEntries = lib.mapAttrsToList (
        name: _host:
        let
          sshKey = lib.attrByPath [ name "public" "sshHostKey" ] null sshHostServices;
          yggPublic = lib.attrByPath [ name "public" ] { } yggServices;
          yggAddress = yggPublic.deployHost or (yggPublic.yggdrasilAddress or null);
          fallbackTarget = lib.attrByPath [ name "targetHost" ] null bootstrapInventory;
          aliases = lib.attrByPath [ name "aliases" ] [ ] privateYggNodes;
          hostPatterns = lib.unique (
            [ name ]
            ++ aliases
            ++ lib.optional (yggAddress != null) yggAddress
            ++ lib.optional (yggAddress != null && lib.hasInfix ":" yggAddress) "[${yggAddress}]"
            ++ lib.optional (fallbackTarget != null) fallbackTarget
          );
        in
        if sshKey == null || hostPatterns == [ ] then
          null
        else
          "${lib.concatStringsSep "," hostPatterns} ${sshKey}"
      ) site.hosts;
    in
    lib.concatStringsSep "\n" (lib.filter (entry: entry != null) hostEntries) + "\n";
  registryGitSshCommand =
    let
      identityArgs = lib.optionalString (
        registryTransportIdentityFile != null
      ) "-i ${registryTransportIdentityFile} ";
    in
    "ssh "
    + identityArgs
    + "-o IdentitiesOnly=yes "
    + "-o IdentityAgent=none "
    + "-o BatchMode=yes "
    + "-o PreferredAuthentications=publickey "
    + "-o StrictHostKeyChecking=yes "
    + "-o UserKnownHostsFile=${registryKnownHostsFile} "
    + "-o GlobalKnownHostsFile=${registryKnownHostsFile}";
  gitEnvironment = ''
    export HOME=/root
    export GIT_CONFIG_GLOBAL=/var/lib/cluster-identity/gitconfig
  '';
  desiredIdentityServices = lib.unique (
    (lib.optional (
      builtins.elem "system/cluster-identity" (hostInventory.dendrites or [ ])
      || hostClusterIdentity ? role
    ) "host-age")
    ++ (lib.optional (
      lib.attrByPath [ "ssh" "enableLiveKnownHosts" ] false serviceFlags
      || lib.attrByPath [ "ssh" "enableLiveIdentity" ] false serviceFlags
    ) "ssh-host")
    ++ (lib.optional (
      lib.attrByPath [ "yggdrasil" "enableLiveIdentity" ] false serviceFlags
      || builtins.elem "privateYggdrasil" (hostInventory.networks or [ ])
    ) "yggdrasil")
    ++ (lib.optional (
      lib.attrByPath [ "radicle" "enableLiveIdentity" ] false serviceFlags
      || builtins.elem "network/radicle" (hostInventory.dendrites or [ ])
      || lib.attrByPath [ "org" "network" "radicle" "seed" ] false hostInventory
    ) "radicle")
    ++ (lib.optional (
      lib.attrByPath [ "gitAnnex" "enableLiveIdentity" ] false serviceFlags
      || builtins.elem "storage/git-annex" (hostInventory.dendrites or [ ])
    ) "git-annex")
  );
  missingIdentityServices = builtins.filter (
    service:
    let
      serviceRecords = identityServices.${service} or { };
    in
    !(builtins.hasAttr hostName serviceRecords)
  ) desiredIdentityServices;
in
{
  options.my.clusterIdentity = {
    enable = lib.mkOption {
      type = lib.types.bool;
      default = registryPolicy.enable or true;
      description = "Enable the live signed cluster identity registry agent.";
    };

    role = lib.mkOption {
      type = lib.types.enum [
        "leader"
        "follower"
        "bootstrap-only"
      ];
      default = hostClusterIdentity.role or "follower";
      description = "Registry role for this host.";
    };

    registryPath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.path or "/var/lib/cluster-identity/registry";
      description = "Local clone of the cluster identity registry.";
    };

    materializedPath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.materializedPath or "/run/cluster-identity";
      description = "Runtime directory containing materialized trusted identity state.";
    };

    trustedLeaders = lib.mkOption {
      type = lib.types.attrs;
      default = inventoryPolicy.leaders or { };
      description = "Leader signing policy from inventory.";
    };

    policy = lib.mkOption {
      type = lib.types.attrs;
      default = inventoryPolicy.policy or { };
      description = "Cluster identity registry promotion and conflict policy.";
    };

    fetchInterval = lib.mkOption {
      type = lib.types.str;
      default = lib.attrByPath [
        "fetch"
        "interval"
      ] "2min" registryPolicy;
      description = "Interval for follower-safe registry sync.";
    };

    randomizedDelay = lib.mkOption {
      type = lib.types.str;
      default = lib.attrByPath [
        "fetch"
        "randomizedDelay"
      ] "30s" registryPolicy;
      description = "Randomized delay for registry sync timer.";
    };

    sopsDefaultFile = lib.mkOption {
      type = lib.types.path;
      default = ../../../../inventory/keys/identities/cluster-private-identities.sops.yaml;
      description = "Default SOPS file for leader-encrypted private identity material.";
    };

    sopsAgeKeyFile = lib.mkOption {
      type = lib.types.str;
      default = hostAgeEncryption.privateKeyPath or "/var/lib/cluster-identity/age/host.agekey";
      description = "Host-local age identity used by sops-nix and private identity delivery.";
    };

    flakePath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.flakePath or "/work/flake";
      description = "Local flake checkout used by leader auto-publish.";
    };

    signingKeyPath = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default =
        let
          hostSigningKey = lib.attrByPath [
            hostName
            "signingKeyPath"
          ] null leaderPolicy;
          policySigningKey = lib.attrByPath [
            "policy"
            "signingKeyPath"
          ] null inventoryPolicy;
        in
        if hostSigningKey != null then hostSigningKey else policySigningKey;
      description = "Host-local OpenSSH private key used to sign registry events.";
    };

    registryTransportIdentityFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = defaultRegistryTransportIdentityFile;
      description = "Host-local OpenSSH private key used for registry Git fetch and push transport.";
    };

    autoPublishOnActivation = lib.mkOption {
      type = lib.types.bool;
      default =
        hostClusterIdentity.autoPublishOnActivation or (hostClusterIdentity.role or "follower") == "leader";
      description = "Publish the flake identity ledger to the live registry during leader activation.";
    };
  };

  config = lib.mkIf cfg.enable {
    warnings = lib.optional (missingIdentityServices != [ ]) ''
      cluster identity source records are missing for ${hostName}: ${lib.concatStringsSep ", " missingIdentityServices}
      Run `clusterctl identity generate-missing --node ${hostName}` from a leader, then `clusterctl identity matrix --node ${hostName}` to confirm.
    '';

    environment.systemPackages = [
      clusterctlPackage
      pkgs.git
      pkgs.openssh
      pkgs.sops
      pkgs.ssh-to-age
      pkgs.age
    ];

    environment.variables.SOPS_AGE_KEY_FILE = cfg.sopsAgeKeyFile;

    sops = {
      defaultSopsFile = cfg.sopsDefaultFile;
      age.keyFile = cfg.sopsAgeKeyFile;
    };

    systemd.tmpfiles.rules = [
      "d /var/lib/cluster-identity 0700 root root -"
      "d /var/lib/cluster-identity/age 0700 root root -"
      "d ${cfg.registryPath} 0700 root root -"
      "d ${cfg.materializedPath} 0755 root root -"
    ];

    environment.etc."cluster-identity/policy.json".source =
      json.generate "cluster-identity-policy.json"
        {
          hostName = config.networking.hostName;
          role = cfg.role;
          trustedLeaders = cfg.trustedLeaders;
          policy = cfg.policy;
          registry = registryPolicy // {
            transport = (registryPolicy.transport or { }) // {
              knownHostsFile = registryKnownHostsFile;
              identityFile = registryTransportIdentityFile;
              gitSshCommand = registryGitSshCommand;
            };
          };
          registryPath = cfg.registryPath;
          materializedPath = cfg.materializedPath;
          sopsAgeKeyFile = cfg.sopsAgeKeyFile;
          signingKeyPath = cfg.signingKeyPath;
        };

    environment.etc."cluster-identity/registry-known-hosts".text = registryKnownHostsText;

    programs.ssh.extraConfig = lib.mkIf sshLiveKnownHosts (
      lib.mkAfter ''
        Host *
          GlobalKnownHostsFile ${cfg.materializedPath}/ssh_known_hosts /etc/ssh/ssh_known_hosts
      ''
    );

    systemd.services.cluster-identity-fetch = {
      description = "Fetch and materialize the live cluster identity registry";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
      };
      path = [
        clusterctlPackage
        pkgs.git
        pkgs.openssh
      ];
      script = ''
        set -u
        ${gitEnvironment}
        git config --global --add safe.directory "${cfg.registryPath}" || true
        clusterctl registry remotes sync \
          --registry "${cfg.registryPath}" \
          --policy /etc/cluster-identity/policy.json || true
        clusterctl registry sync \
          --registry "${cfg.registryPath}" \
          --out "${cfg.materializedPath}" \
          --policy /etc/cluster-identity/policy.json || true
      '';
    };

    systemd.services.cluster-identity-push = lib.mkIf (cfg.role == "leader") {
      description = "Push the live cluster identity registry from a leader";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
      };
      path = [
        clusterctlPackage
        pkgs.git
        pkgs.openssh
      ];
      script = ''
        set -u
        ${gitEnvironment}
        git config --global --add safe.directory "${cfg.registryPath}" || true
        clusterctl registry push \
          --registry "${cfg.registryPath}" \
          --policy /etc/cluster-identity/policy.json || true
      '';
    };

    systemd.timers.cluster-identity-push =
      lib.mkIf
        (
          cfg.role == "leader"
          && lib.attrByPath [
            "push"
            "enableTimer"
          ] true registryPolicy
        )
        {
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnBootSec = lib.attrByPath [
              "push"
              "onBootSec"
            ] "3min" registryPolicy;
            OnUnitActiveSec = lib.attrByPath [
              "push"
              "interval"
            ] "5min" registryPolicy;
            RandomizedDelaySec = lib.attrByPath [
              "push"
              "randomizedDelay"
            ] "1min" registryPolicy;
            Persistent = true;
          };
        };

    systemd.timers.cluster-identity-fetch =
      lib.mkIf
        (lib.attrByPath [
          "fetch"
          "enableTimer"
        ] true registryPolicy)
        {
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnBootSec = "1min";
            OnUnitActiveSec = cfg.fetchInterval;
            RandomizedDelaySec = cfg.randomizedDelay;
            Persistent = true;
          };
        };

    systemd.services.cluster-identity-fetch-now = {
      description = "Immediately fetch and materialize the live cluster identity registry";
      serviceConfig = {
        Type = "oneshot";
      };
      script = ''
        systemctl start cluster-identity-fetch.service
      '';
    };

    system.activationScripts.cluster-identity-init-registry = {
      deps = [ "etc" ];
      text = ''
        PATH="${
          lib.makeBinPath [
            clusterctlPackage
            pkgs.git
            pkgs.openssh
          ]
        }:$PATH"
        ${gitEnvironment}

        if [ ! -d "${cfg.registryPath}/.git" ]; then
          install -d -m 0700 "${cfg.registryPath}"
          clusterctl registry init \
            --registry "${cfg.registryPath}" \
            --no-commit
        else
          git -C "${cfg.registryPath}" config --local receive.denyCurrentBranch updateInstead || true
        fi
      '';
    };

    system.activationScripts.cluster-identity-publish = lib.mkIf cfg.autoPublishOnActivation {
      deps = [
        "etc"
        "cluster-identity-init-registry"
      ];
      text = ''
        if [ -d "${cfg.flakePath}" ]; then
          PATH="${
            lib.makeBinPath [
              clusterctlPackage
              config.nix.package
              pkgs.git
              pkgs.openssh
            ]
          }:$PATH"
          ${gitEnvironment}
          git config --global --add safe.directory "${cfg.registryPath}" || true
          clusterctl --flake "${cfg.flakePath}" identity publish \
            --registry "${cfg.registryPath}" \
            --out "${cfg.materializedPath}" \
            --policy /etc/cluster-identity/policy.json || true
        fi
      '';
    };
  };
}
