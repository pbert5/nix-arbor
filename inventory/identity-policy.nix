{
  clusterId = "ash-homelab";

  registry = {
    enable = true;

    path = "/var/lib/cluster-identity/registry";
    materializedPath = "/run/cluster-identity";
    localStatePath = "/var/lib/cluster-identity/local-state";
    snapshotPath = "/var/lib/cluster-identity/publisher/snapshot";
    publisherStatePath = "/var/lib/cluster-identity/publisher-state";
    followerCachePath = "/var/lib/cluster-identity/follower-cache";
    acceptedRegistryPath = "/var/lib/cluster-identity/accepted-registry";

    transports = {
      ipfs = true;
      ipns = true;
      pubsub = true;
      onionMirrors = true;
      gitSshYggdrasil = false;
      radicle = false;
      fallbackSsh = false;
    };

    fetch = {
      enableTimer = true;
      interval = "2min";
      randomizedDelay = "30s";
    };

    push = {
      enableTimer = true;
      interval = "5min";
      randomizedDelay = "1min";
    };

    ipfs = {
      api = "/unix/run/ipfs.sock";
      ipnsLifetime = "168h";
      ipnsTtl = "5m";
      resolveTimeoutSeconds = 60;
      swarmPort = 4001;
    };

    pubsub = {
      enable = true;
      topic = "cluster-identity/ash-homelab/roots/v1";
      maxHintAgeSeconds = 600;
      maxFutureSkewSeconds = 60;
      maxMessageBytes = 65536;
      publishTimeoutSeconds = 15;
      reconnectDelaySeconds = 5;
      listenerRestartSec = "5s";
    };

    onion = {
      mirrorPath = "/var/lib/cluster-identity/onion-mirror";
      socksProxy = "127.0.0.1:9050";
      connectTimeoutSeconds = 20;
      fetchTimeoutSeconds = 120;
      maxHeadBytes = 1048576;
      maxRootBytes = 4194304;
      maxObjectBytes = 1073741824;
      maxConcurrentConnections = 8;
      requestsPerSecond = 8;
      requestBurst = 16;
      bytesPerSecond = "2m";
      torMaxStreams = 16;
      torMaxStreamsCloseCircuit = true;
    };

    apply = {
      reloadServices = [ ];
    };

    notify = {
      enable = true;
      serviceName = "cluster-identity-fetch-now.service";
    };

    # remotes are derived in lib/identity-policy.nix from hosts where
    # org.clusterIdentity.role = "leader", using identity-services/yggdrasil.nix
    # for overlay addresses and host-bootstrap.nix for fallback IPs.
  };

  # leaders are derived in lib/identity-policy.nix from hosts where
  # org.clusterIdentity.role = "leader"; signing keys are read from leaderSigningKeysDir.
  leaderSigningKeysDir = ./keys/leaders;

  policy = {
    requireReceiptBeforePromote = true;
    burnedAlwaysWins = true;
    allowDeprecatedFallback = true;
    maxDeprecatedFallbackGenerations = 2;
    policyGeneration = 1;
    allowPlaceholderSignatures = false;
    signingKeyPath = "/home/example/.ssh/deploy_rsa";
    sameGenerationConflict = "freeze-subject";
    allowRollback = false;
    thresholds = {
      publicIdentityUpdate = 1;
      servicePrivateRotation = 1;
      burnServiceKey = 1;
      hostAgeRotation = 2;
      leaderPolicyUpdate = 1;
    };
  };
}
