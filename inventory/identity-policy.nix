{
  registry = {
    enable = true;

    path = "/var/lib/cluster-identity/registry";
    materializedPath = "/run/cluster-identity";

    transports = {
      gitSshYggdrasil = true;
      radicle = true;
      fallbackSsh = true;
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
    leaderPolicyEpoch = 1;
    allowPlaceholderSignatures = false;
    signingKeyPath = "/home/example/.ssh/deploy_rsa";
  };
}
