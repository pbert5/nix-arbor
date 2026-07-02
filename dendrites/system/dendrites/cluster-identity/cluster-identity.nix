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
  clusterctlPackage = pkgs.callPackage ../../../../tools/clusterctl/clusterctl-package.nix {
    defaultFlake = clusterctlFlake;
  };
  hostClusterIdentity = lib.attrByPath [ "org" "clusterIdentity" ] { } hostInventory;
  inventoryPolicy = site.identityPolicy or { };
  inventoryIdentities = site.identities or { };
  identityEncryption = inventoryIdentities.encryption or { };
  hostAgeEncryption = identityEncryption.hostAge or { };
  registryPolicy = inventoryPolicy.registry or { };
  leaderPolicy = inventoryPolicy.leaders or { };
  bootstrapInventory = site.hostBootstrap or { };
  privateYggNodes = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" ] { } site;
  hostName = config.networking.hostName;
  hostIdentityRequirements = lib.attrByPath [ "identityRequirements" "byHost" hostName ] { } site;
  sshHostServices = lib.attrByPath [ "ssh-host" ] { } identityServices;
  yggServices = lib.attrByPath [ "yggdrasil" ] { } identityServices;
  sshLiveKnownHosts = builtins.hasAttr "ssh-host" hostIdentityRequirements;
  identityServices = inventoryIdentities.services or { };
  ipnsPublisherServices = lib.attrByPath [ "ipns-publisher" ] { } identityServices;
  statusIpnsServices = lib.attrByPath [ "status-ipns" ] { } identityServices;
  statusIpnsRecord = statusIpnsServices.${hostName} or { };
  statusIpnsPublic = statusIpnsRecord.public or { };
  statusIpnsPrivate = statusIpnsRecord.private or { };
  leaderUserSshServices = lib.attrByPath [ "leader-user-ssh" ] { } identityServices;
  leaderUserSshRecord = leaderUserSshServices.${hostName} or { };
  leaderUserNames = builtins.filter (
    userName:
    lib.attrByPath [
      "users"
      userName
      "org"
      "clusterIdentity"
      "role"
    ] null site == "leader"
  ) (hostInventory.users or [ ]);
  leaderUserName =
    if builtins.length leaderUserNames == 1 then builtins.head leaderUserNames else null;
  leaderUserSshPublic = leaderUserSshRecord.public or { };
  leaderUserSshPrivate = leaderUserSshRecord.private or { };
  leaderUserSshTargetPath =
    if leaderUserName == null then
      null
    else
      leaderUserSshPrivate.targetPath
        or "${site.users.${leaderUserName}.home.directory}/.ssh/cluster-leader-ed25519";
  leaderUserSshEnabled =
    isLeader
    && leaderUserName != null
    && leaderUserSshRecord != { }
    && (leaderUserSshPublic.user or null) == leaderUserName
    && leaderUserSshTargetPath != null;
  leaderUserOperational = isLeader && leaderUserName != null;
  leaderStateOwner = if leaderUserOperational then leaderUserName else "root";
  leaderStateGroup = if leaderUserOperational then "cluster-identity" else "root";
  leaderStateMode = if leaderUserOperational then "0770" else "0700";
  leaderServiceHome =
    if leaderUserOperational then site.users.${leaderUserName}.home.directory else "/root";
  clusterctlFlake =
    if leaderUserName == null then
      "."
    else
      lib.attrByPath [
        "users"
        leaderUserName
        "org"
        "flakeTarget"
        "path"
      ] "${site.users.${leaderUserName}.home.directory}/flake" site;
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
    + "-o ConnectTimeout=5 "
    + "-o ConnectionAttempts=1 "
    + "-o PreferredAuthentications=publickey "
    + "-o StrictHostKeyChecking=yes "
    + "-o UserKnownHostsFile=${registryKnownHostsFile} "
    + "-o GlobalKnownHostsFile=${registryKnownHostsFile}";
  gitEnvironment = ''
    export HOME=/root
    export GIT_CONFIG_COUNT=1
    export GIT_CONFIG_KEY_0=safe.directory
    export GIT_CONFIG_VALUE_0="${cfg.registryPath}"
  '';
  desiredIdentityServices = builtins.attrNames hostIdentityRequirements;
  missingIdentityServices = builtins.filter (
    service:
    let
      serviceRecords = identityServices.${service} or { };
    in
    !(builtins.hasAttr hostName serviceRecords)
  ) desiredIdentityServices;
  isLeader = cfg.role == "leader";
  leaderIpnsName = lib.attrByPath [ hostName "ipnsName" ] null cfg.trustedLeaders;
  ipfsPolicy = registryPolicy.ipfs or { };
  pubsubPolicy = registryPolicy.pubsub or { };
  onionPolicy = registryPolicy.onion or { };
  transports = registryPolicy.transports or { };
  ipfsEnabled = cfg.role != "bootstrap-only" && (transports.ipfs or true);
  registryFetchEnabled = cfg.role != "bootstrap-only" && ipfsEnabled;
  configuredOnionMirrors = lib.filter (value: value != null) (
    lib.mapAttrsToList (_: leader: leader.onionMirror or null) leaderPolicy
  );
  onionMirrorsEnabled = transports.onionMirrors or false;
  onionClientEnabled = registryFetchEnabled && onionMirrorsEnabled && configuredOnionMirrors != [ ];
  enrolledOnionMirror = lib.attrByPath [ hostName "onionMirror" ] null leaderPolicy;
  onionMirrorEnabled =
    isLeader
    && onionMirrorsEnabled
    && ((hostClusterIdentity.onionMirrorService or false) || enrolledOnionMirror != null);
  expectedOnionHost =
    if enrolledOnionMirror == null then
      null
    else
      lib.removeSuffix "/" (lib.removePrefix "http://" enrolledOnionMirror);
  onionMirrorPort = lib.attrByPath [
    "ports"
    "clusterIdentityOnionMirror"
    "port"
  ] 17650 site;
  pubsubEnabled =
    registryFetchEnabled && (transports.pubsub or false) && (pubsubPolicy.enable or false);
  ipnsPublicationEnabled = isLeader && leaderIpnsName != null && cfg.ipnsKeySopsFile != null;
  statusPublicationEnabled =
    cfg.role != "bootstrap-only" && ipfsEnabled && statusIpnsPublic ? ipnsName;
  statusIpnsPrivateSopsFile =
    if
      (statusIpnsPrivate.sopsPath or null)
      == "inventory/keys/identities/cluster-private-identities.sops.yaml"
    then
      cfg.sopsDefaultFile
    else
      null;
  statusIpnsPrivateKeyEnabled =
    statusPublicationEnabled && statusIpnsPrivateSopsFile != null && statusIpnsPrivate ? sopsKey;
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

    localStatePath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.localStatePath or "/var/lib/cluster-identity/local-state";
      description = "Persistent anti-rollback checkpoints and last-good registry state.";
    };

    snapshotPath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.snapshotPath or "/var/lib/cluster-identity/publisher/snapshot";
      description = "Working directory for the canonical registry snapshot published to IPFS.";
    };

    publisherStatePath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.publisherStatePath or "/var/lib/cluster-identity/publisher-state";
      description = "Persistent leader root sequence and previous-CID state.";
    };

    followerCachePath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.followerCachePath or "/var/lib/cluster-identity/follower-cache";
      description = "Persistent cache of verified immutable registry snapshots by leader and CID.";
    };

    acceptedRegistryPath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.acceptedRegistryPath or "/var/lib/cluster-identity/accepted-registry";
      description = "Locally assembled registry containing only accepted leader-authored content.";
    };

    statusPublisherPath = lib.mkOption {
      type = lib.types.str;
      default = registryPolicy.statusPublisherPath or "/var/lib/cluster-identity/status-publisher/status";
      description = "Working directory for this node's signed IPNS status payload.";
    };

    onionMirrorPath = lib.mkOption {
      type = lib.types.str;
      default = onionPolicy.mirrorPath or "/var/lib/cluster-identity/onion-mirror";
      description = "Read-only tree of signed heads and immutable snapshots served over Tor.";
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
        if hostSigningKey != null then
          hostSigningKey
        else if leaderUserSshEnabled then
          leaderUserSshTargetPath
        else
          policySigningKey;
      description = "Host-local OpenSSH private key used to sign registry events.";
    };

    ipnsKeyName = lib.mkOption {
      type = lib.types.str;
      default = "cluster-identity-${hostName}";
      description = "Kubo keystore name for this leader's enrolled IPNS publishing key.";
    };

    statusIpnsKeyName = lib.mkOption {
      type = lib.types.str;
      default = statusIpnsPublic.keyName or "cluster-identity-status-${hostName}";
      description = "Kubo keystore name for this node's status IPNS publisher.";
    };

    ipnsKeySopsFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default =
        if hostClusterIdentity ? ipnsKeySopsFile then
          hostClusterIdentity.ipnsKeySopsFile
        else if builtins.hasAttr hostName ipnsPublisherServices then
          ../../../../inventory/keys/leaders/leader-ipns-keys.sops.yaml
        else
          null;
      description = "Optional SOPS file containing this leader's PEM PKCS8 IPNS private key under its hostname.";
    };

    registryTransportIdentityFile = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = defaultRegistryTransportIdentityFile;
      description = "Host-local OpenSSH private key used for registry Git fetch and push transport.";
    };

    publishRunAsRoot = lib.mkOption {
      type = lib.types.bool;
      default = hostClusterIdentity.publishRunAsRoot or false;
      description = "Run the publish service as root instead of the leader user. Use when the signing key is only accessible by root.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = !isLeader || builtins.length leaderUserNames == 1;
        message = "${hostName} must select exactly one user with org.clusterIdentity.role = \"leader\".";
      }
      {
        assertion =
          leaderUserSshRecord == { }
          || (leaderUserName != null && (leaderUserSshPublic.user or null) == leaderUserName);
        message = "${hostName}'s leader-user-ssh identity does not match its declared leader user.";
      }
      {
        assertion = lib.all (
          value: builtins.match "^http://[a-z2-7]{56}\\.onion/?$" value != null
        ) configuredOnionMirrors;
        message = "Cluster identity onion mirrors must be v3 http://*.onion URLs.";
      }
    ];

    warnings =
      lib.optional (missingIdentityServices != [ ]) ''
        cluster identity source records are missing for ${hostName}: ${lib.concatStringsSep ", " missingIdentityServices}
        Run `clusterctl identity generate-missing --node ${hostName}` from a leader, then `clusterctl identity matrix --node ${hostName}` to confirm.
      ''
      ++ lib.optional (isLeader && !ipnsPublicationEnabled) ''
        ${hostName} is a cluster identity leader but IPNS publication is not enrolled.
        Run `clusterctl identity generate-missing --node ${hostName} --service ipns-publisher --no-publish`, then deploy the generated flake state.
      '';

    environment.systemPackages = [
      clusterctlPackage
      pkgs.git
      pkgs.openssh
      pkgs.sops
      pkgs.ssh-to-age
      pkgs.age
      pkgs.kubo
      pkgs.curl
    ];

    users.groups.cluster-identity = { };
    users.users.${leaderUserName}.extraGroups = lib.mkIf leaderUserOperational (
      lib.mkAfter [
        "cluster-identity"
        "ipfs"
      ]
    );

    environment.variables.SOPS_AGE_KEY_FILE = cfg.sopsAgeKeyFile;

    sops = {
      defaultSopsFile = cfg.sopsDefaultFile;
      age.keyFile = cfg.sopsAgeKeyFile;
    };

    systemd.tmpfiles.rules = [
      "d /var/lib/cluster-identity ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d /var/lib/cluster-identity/age 0750 root ${leaderStateGroup} -"
      "d ${cfg.localStatePath} ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d ${cfg.localStatePath}/last-good ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d ${cfg.publisherStatePath} ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d ${builtins.dirOf cfg.snapshotPath} ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d ${builtins.dirOf cfg.statusPublisherPath} 0750 root root -"
      "d ${cfg.followerCachePath} ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d ${cfg.acceptedRegistryPath} ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d ${cfg.onionMirrorPath} ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d ${cfg.registryPath} ${leaderStateMode} ${leaderStateOwner} ${leaderStateGroup} -"
      "d ${cfg.materializedPath} 0775 ${leaderStateOwner} ${leaderStateGroup} -"
    ]
    ++ lib.optional leaderUserOperational "z ${cfg.sopsAgeKeyFile} 0640 root ${leaderStateGroup} -"
    ++ lib.optional leaderUserSshEnabled "d ${builtins.dirOf leaderUserSshTargetPath} 0700 ${leaderUserName} users -"
    ++ [ "r /var/lib/cluster-identity/gitconfig.lock" ];

    environment.etc."cluster-identity/policy.json".source =
      json.generate "cluster-identity-policy.json"
        {
          clusterId = inventoryPolicy.clusterId;
          hostName = config.networking.hostName;
          role = cfg.role;
          trustedLeaders = cfg.trustedLeaders;
          policy = cfg.policy;
          registry = registryPolicy // {
            snapshotPath = cfg.snapshotPath;
            publisherStatePath = cfg.publisherStatePath;
            followerCachePath = cfg.followerCachePath;
            acceptedRegistryPath = cfg.acceptedRegistryPath;
            statusPublisherPath = cfg.statusPublisherPath;
            onion = onionPolicy // {
              mirrorPath = cfg.onionMirrorPath;
            };
            ipfs = ipfsPolicy // {
              keyName = cfg.ipnsKeyName;
            };
            transport = (registryPolicy.transport or { }) // {
              knownHostsFile = registryKnownHostsFile;
              identityFile = registryTransportIdentityFile;
              gitSshCommand = registryGitSshCommand;
            };
          };
          registryPath = cfg.registryPath;
          materializedPath = cfg.materializedPath;
          localStatePath = cfg.localStatePath;
          statusPublishers = inventoryPolicy.statusPublishers or { };
          sopsAgeKeyFile = cfg.sopsAgeKeyFile;
          signingKeyPath = cfg.signingKeyPath;
          receiptSigningKeyPath = "/etc/ssh/ssh_host_ed25519_key";
        };

    environment.etc."cluster-identity/registry-known-hosts".text = registryKnownHostsText;

    sops.secrets.cluster-identity-ipns-key = lib.mkIf ipnsPublicationEnabled {
      sopsFile = cfg.ipnsKeySopsFile;
      key = hostName;
      owner = "root";
      mode = "0400";
      restartUnits = [ "cluster-identity-ipns-key.service" ];
    };

    sops.secrets.cluster-identity-leader-user-ssh = lib.mkIf leaderUserSshEnabled {
      sopsFile = cfg.sopsDefaultFile;
      key = leaderUserSshPrivate.sopsKey or "${hostName}-leader-user-ssh";
      owner = leaderUserName;
      mode = "0600";
      path = leaderUserSshTargetPath;
    };

    sops.secrets.cluster-identity-leader-user-ssh-nix-build = lib.mkIf leaderUserSshEnabled {
      sopsFile = cfg.sopsDefaultFile;
      key = leaderUserSshPrivate.sopsKey or "${hostName}-leader-user-ssh";
      owner = "root";
      mode = "0400";
    };

    sops.secrets.cluster-identity-status-ipns-key = lib.mkIf statusIpnsPrivateKeyEnabled {
      sopsFile = statusIpnsPrivateSopsFile;
      key = statusIpnsPrivate.sopsKey;
      owner = "root";
      mode = "0400";
      restartUnits = [ "cluster-identity-status-ipns-key.service" ];
    };

    services.kubo = lib.mkIf ipfsEnabled {
      enable = true;
      enableGC = true;
      extraFlags = lib.optional pubsubEnabled "--enable-pubsub-experiment";
      localDiscovery = false;
      settings = {
        Datastore.StorageMax = "20GB";
        Discovery.MDNS.Enabled = false;
        Pubsub.Enabled = pubsubEnabled;
      };
    };

    services.tor = lib.mkIf (onionClientEnabled || onionMirrorEnabled) {
      enable = true;
      client.enable = true;
      relay.onionServices.cluster-identity = lib.mkIf onionMirrorEnabled {
        version = 3;
        settings = {
          HiddenServiceMaxStreams = onionPolicy.torMaxStreams or 16;
          HiddenServiceMaxStreamsCloseCircuit = onionPolicy.torMaxStreamsCloseCircuit or true;
        };
        map = [
          {
            port = 80;
            target = {
              addr = "127.0.0.1";
              port = onionMirrorPort;
            };
          }
        ];
      };
    };

    services.nginx = lib.mkIf onionMirrorEnabled {
      enable = true;
      group = "cluster-identity";
      appendHttpConfig = ''
        limit_conn_zone $binary_remote_addr zone=cluster_identity_onion_conn:1m;
        limit_req_zone $binary_remote_addr zone=cluster_identity_onion_req:1m rate=${
          toString (onionPolicy.requestsPerSecond or 8)
        }r/s;
      '';
      virtualHosts.cluster-identity-onion = {
        listen = [
          {
            addr = "127.0.0.1";
            port = onionMirrorPort;
          }
        ];
        root = cfg.onionMirrorPath;
        locations."/".extraConfig = ''
          autoindex off;
          limit_conn cluster_identity_onion_conn ${toString (onionPolicy.maxConcurrentConnections or 8)};
          limit_conn_status 429;
          limit_req zone=cluster_identity_onion_req burst=${
            toString (onionPolicy.requestBurst or 16)
          } nodelay;
          limit_req_status 429;
          limit_rate ${onionPolicy.bytesPerSecond or "2m"};
          limit_except GET {
            deny all;
          }
        '';
      };
    };

    networking.firewall.allowedTCPPorts = lib.mkIf ipfsEnabled [ (ipfsPolicy.swarmPort or 4001) ];
    networking.firewall.allowedUDPPorts = lib.mkIf ipfsEnabled [ (ipfsPolicy.swarmPort or 4001) ];

    programs.ssh.extraConfig = lib.mkIf sshLiveKnownHosts (
      lib.mkBefore ''
        Include ${cfg.materializedPath}/ssh_config

        Host *
          GlobalKnownHostsFile ${cfg.materializedPath}/ssh_known_hosts /etc/ssh/ssh_known_hosts
      ''
    );

    systemd.services.cluster-identity-fetch = {
      description = "Resolve, verify, and materialize trusted cluster identity IPNS heads";
      after = [ "network-online.target" ] ++ lib.optional ipfsEnabled "ipfs.service";
      wants = [ "network-online.target" ];
      requires = lib.optional ipfsEnabled "ipfs.service";
      serviceConfig = {
        Type = "oneshot";
        User = lib.mkIf leaderUserOperational leaderUserName;
        Group = lib.mkIf leaderUserOperational "users";
        SupplementaryGroups = lib.mkIf leaderUserOperational [
          "cluster-identity"
          "ipfs"
        ];
        Environment = "HOME=${leaderServiceHome}";
        UMask = "0022";
        ExecStartPost = [
          "+${pkgs.coreutils}/bin/chown root:root ${cfg.materializedPath}/ssh_config"
          "+${pkgs.coreutils}/bin/chmod 0644 ${cfg.materializedPath}/ssh_config"
        ];
      };
      path = [
        clusterctlPackage
        pkgs.git
        pkgs.kubo
        pkgs.curl
        pkgs.openssh
      ];
      script = ''
        set -u
        ${lib.optionalString ipfsEnabled ''
          if clusterctl registry fetch-ipfs \
            --out "${cfg.materializedPath}" \
            --cache-dir "${cfg.followerCachePath}" \
            --accepted-registry "${cfg.acceptedRegistryPath}" \
            --policy /etc/cluster-identity/policy.json; then
            exit 0
          fi
        ''}
        exit 1
      '';
    };

    systemd.services.cluster-identity-ipns-key = lib.mkIf ipnsPublicationEnabled {
      description = "Import and verify the cluster identity IPNS publishing key";
      after = [ "ipfs.service" ];
      requires = [ "ipfs.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        Environment = "HOME=/root";
        Restart = "on-failure";
        RestartSec = "5s";
      };
      path = [
        clusterctlPackage
        pkgs.kubo
      ];
      script = ''
        clusterctl registry ipns-key ensure \
          --policy /etc/cluster-identity/policy.json \
          --publisher "${hostName}" \
          --key-name "${cfg.ipnsKeyName}" \
          --key-file "${config.sops.secrets.cluster-identity-ipns-key.path}" \
          --expected-name "${leaderIpnsName}"
      '';
    };

    systemd.services.cluster-identity-publish = lib.mkIf ipnsPublicationEnabled {
      description = "Publish a signed cluster identity registry snapshot to IPFS and IPNS";
      after = [
        "network-online.target"
        "ipfs.service"
        "cluster-identity-ipns-key.service"
        "cluster-identity-prepare-leader-state.service"
      ]
      ++ lib.optional (enrolledOnionMirror != null) "cluster-identity-onion-address.service";
      wants = [ "network-online.target" ];
      requires = [
        "ipfs.service"
        "cluster-identity-ipns-key.service"
        "cluster-identity-prepare-leader-state.service"
      ]
      ++ lib.optional (enrolledOnionMirror != null) "cluster-identity-onion-address.service";
      serviceConfig = {
        Type = "oneshot";
        User = lib.mkIf (leaderUserOperational && !cfg.publishRunAsRoot) leaderUserName;
        Group = lib.mkIf (leaderUserOperational && !cfg.publishRunAsRoot) "users";
        SupplementaryGroups = lib.mkIf (leaderUserOperational && !cfg.publishRunAsRoot) [
          "cluster-identity"
          "ipfs"
        ];
        Environment = "HOME=${if cfg.publishRunAsRoot then "/root" else leaderServiceHome}";
      };
      path = [
        clusterctlPackage
        pkgs.kubo
        pkgs.openssh
      ];
      script = ''
        clusterctl registry publish-ipfs \
          --registry "${cfg.registryPath}" \
          --snapshot-dir "${cfg.snapshotPath}" \
          --policy /etc/cluster-identity/policy.json \
          --publisher "${hostName}"
      '';
    };

    systemd.services.cluster-identity-onion-address = lib.mkIf (enrolledOnionMirror != null) {
      description = "Verify the enrolled cluster identity onion service address";
      after = [ "tor.service" ];
      requires = [ "tor.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      path = [ pkgs.coreutils ];
      script = ''
        actual="$(cat /var/lib/tor/onion/cluster-identity/hostname)"
        if [ "$actual" != "${expectedOnionHost}" ]; then
          echo "Enrolled onion address ${expectedOnionHost} does not match Tor service $actual" >&2
          exit 1
        fi
      '';
    };

    systemd.services.cluster-identity-prepare-leader-state = lib.mkIf leaderUserOperational {
      description = "Prepare writable cluster identity leader state";
      serviceConfig.Type = "oneshot";
      script = ''
        for path in \
          "${cfg.registryPath}" \
          "${cfg.localStatePath}" \
          "${cfg.publisherStatePath}" \
          "${builtins.dirOf cfg.snapshotPath}" \
          "${cfg.followerCachePath}" \
          "${cfg.acceptedRegistryPath}"; do
          if [ -e "$path" ]; then
            chown -R ${leaderStateOwner}:${leaderStateGroup} "$path"
            chmod -R u+rwX,g+rwX,o-rwx "$path"
          fi
        done
        if [ -e "${cfg.materializedPath}" ]; then
          chown -R ${leaderStateOwner}:${leaderStateGroup} "${cfg.materializedPath}"
          chmod -R u+rwX,g+rX,o+rX "${cfg.materializedPath}"
          find "${cfg.materializedPath}" -type d -exec chmod g+w {} +
        fi
      '';
    };

    systemd.timers.cluster-identity-publish =
      lib.mkIf
        (
          ipnsPublicationEnabled
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

    systemd.services.cluster-identity-status-publish = lib.mkIf statusPublicationEnabled {
      description = "Publish this node's materialized cluster identity status to IPFS and IPNS";
      after = [
        "network-online.target"
        "ipfs.service"
        "cluster-identity-fetch.service"
      ]
      ++ lib.optional statusIpnsPrivateKeyEnabled "cluster-identity-status-ipns-key.service";
      wants = [ "network-online.target" ];
      requires = [
        "ipfs.service"
      ]
      ++ lib.optional statusIpnsPrivateKeyEnabled "cluster-identity-status-ipns-key.service";
      serviceConfig = {
        Type = "oneshot";
        Environment = "HOME=/root";
        SupplementaryGroups = [ "ipfs" ];
      };
      path = [
        clusterctlPackage
        pkgs.kubo
        pkgs.openssh
      ];
      script = ''
        clusterctl registry publish-status \
          --out "${cfg.materializedPath}" \
          --policy /etc/cluster-identity/policy.json \
          --status-dir "${cfg.statusPublisherPath}" \
          --node "${hostName}" \
          --key-name "${cfg.statusIpnsKeyName}" \
          --expected-name "${statusIpnsPublic.ipnsName}"
      '';
    };

    systemd.services.cluster-identity-status-ipns-key = lib.mkIf statusIpnsPrivateKeyEnabled {
      description = "Import and verify this node's status IPNS publishing key";
      after = [ "ipfs.service" ];
      requires = [ "ipfs.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        Environment = "HOME=/root";
        Restart = "on-failure";
        RestartSec = "5s";
      };
      path = [
        clusterctlPackage
        pkgs.kubo
      ];
      script = ''
        clusterctl registry status-ipns-key ensure \
          --policy /etc/cluster-identity/policy.json \
          --node "${hostName}" \
          --key-name "${cfg.statusIpnsKeyName}" \
          --key-file "${config.sops.secrets.cluster-identity-status-ipns-key.path}" \
          --expected-name "${statusIpnsPublic.ipnsName}"
      '';
    };

    systemd.timers.cluster-identity-status-publish =
      lib.mkIf
        (
          statusPublicationEnabled
          && lib.attrByPath [
            "status"
            "enableTimer"
          ] true registryPolicy
        )
        {
          wantedBy = [ "timers.target" ];
          timerConfig = {
            OnBootSec = lib.attrByPath [
              "status"
              "onBootSec"
            ] "4min" registryPolicy;
            OnUnitActiveSec = lib.attrByPath [
              "status"
              "interval"
            ] "5min" registryPolicy;
            RandomizedDelaySec = lib.attrByPath [
              "status"
              "randomizedDelay"
            ] "1min" registryPolicy;
            Persistent = true;
          };
        };

    systemd.timers.cluster-identity-fetch =
      lib.mkIf
        (
          registryFetchEnabled
          && lib.attrByPath [
            "fetch"
            "enableTimer"
          ] true registryPolicy
        )
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

    systemd.services.cluster-identity-pubsub-listener = lib.mkIf pubsubEnabled {
      description = "Verify cluster identity PubSub hints and trigger IPNS convergence";
      wantedBy = [ "multi-user.target" ];
      after = [
        "network-online.target"
        "ipfs.service"
      ];
      wants = [ "network-online.target" ];
      requires = [ "ipfs.service" ];
      serviceConfig = {
        Type = "simple";
        Environment = "HOME=/root";
        Restart = "always";
        RestartSec = pubsubPolicy.listenerRestartSec or "5s";
      };
      path = [
        clusterctlPackage
        pkgs.kubo
        config.systemd.package
      ];
      script = ''
        exec clusterctl registry listen-pubsub \
          --policy /etc/cluster-identity/policy.json \
          --trigger-unit cluster-identity-fetch.service
      '';
    };

    system.activationScripts.cluster-identity-init-registry = lib.mkIf isLeader {
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

        install -d -m ${leaderStateMode} -o ${leaderStateOwner} -g ${leaderStateGroup} "${cfg.registryPath}"
        clusterctl registry ensure-v1 \
          --registry "${cfg.registryPath}"
        chown -R ${leaderStateOwner}:${leaderStateGroup} "${cfg.registryPath}"
        chmod -R u+rwX,g+rwX,o-rwx "${cfg.registryPath}"
      '';
    };

  };
}
