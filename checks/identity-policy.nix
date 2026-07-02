{
  pkgs,
  inventory,
  nixosConfigurations ? { },
}:
let
  identities = inventory.identities or { };
  requirements = inventory.identityRequirements or { };
  policy = inventory.identityPolicy or { };
  registry = policy.registry or { };
  registryRemotes = registry.remotes or { };
  transports = registry.transports or { };
  pubsub = registry.pubsub or { };
  leaders = policy.leaders or { };
  rules = policy.policy or { };
  thresholds = rules.thresholds or { };
  identityServices = identities.services or { };
  hostAgeRecipients = identities.encryption.hostAge.recipients or { };
  privateIdentityLedger = identities.encryption.privateIdentityLedger or { };
  hostAgePrivateLedger = identities.encryption.hostAgePrivateLedger or { };
  leaderIpnsPrivateLedger = identities.encryption.leaderIpnsPrivateLedger or { };
  isAbsolute = value: builtins.isString value && builtins.substring 0 1 value == "/";
  isSopsYaml = value: builtins.isString value && builtins.match ".*\\.sops\\.ya?ml" value != null;
  expectedSourceLedgers = {
    host-age = "inventory/keys/host-age-recipients.nix";
    ipns-publisher = "inventory/identity-services/ipns-publisher.nix";
    onion-mirror = "inventory/identity-services/onion-mirror.nix";
    status-ipns = "inventory/identity-services/status-ipns.nix";
    leader-user-ssh = "inventory/identity-services/leader-user-ssh.nix";
    yggdrasil = "inventory/identity-services/yggdrasil.nix";
    ssh-host = "inventory/identity-services/ssh-host.nix";
    radicle = "inventory/identity-services/radicle.nix";
    git-annex = "inventory/identity-services/git-annex.nix";
  };
  expectedPrivateLedgers = {
    ipns-publisher = leaderIpnsPrivateLedger.path or null;
    status-ipns = privateIdentityLedger.path or null;
    leader-user-ssh = privateIdentityLedger.path or null;
  };
  serviceRecords =
    pkgs.lib.flatten (
      pkgs.lib.mapAttrsToList
        (service: nodes:
          pkgs.lib.mapAttrsToList
            (node: record: {
              inherit service node record;
            })
            nodes)
        identityServices
    );
  validIdentityRecord = item:
    let
      timestamp = item.record.sourceTimestamp or (item.record.keyGeneratedAt or "");
    in
    builtins.isInt (item.record.generation or null)
    && builtins.isString (item.record.state or "")
    && builtins.isString timestamp
    && timestamp != ""
    && (item.record.public or { }) != { };
  requirementRecords =
    pkgs.lib.flatten (
      pkgs.lib.mapAttrsToList
        (
          hostName: requiredServices:
          pkgs.lib.mapAttrsToList
            (service: requirement: {
              inherit hostName service requirement;
              record = identityServices.${service}.${hostName} or { };
            })
            requiredServices
        )
        (requirements.byHost or { })
    );
  dendriteRequirementRecords =
    pkgs.lib.flatten (
      pkgs.lib.mapAttrsToList
        (
          dendrite: dendriteRequirements:
          builtins.map
            (requirement: {
              inherit dendrite requirement;
              service = requirement.service or null;
            })
            dendriteRequirements
        )
        (requirements.byDendrite or { })
    );
  validDendriteRequirement =
    item:
    let
      service = item.service;
    in
    builtins.isString service
    && service != ""
    && (item.requirement.generator or null) == service
    && (item.requirement.sourceLedger or null) == (expectedSourceLedgers.${service} or null)
    && (
      !(item.requirement ? privateLedger)
      || item.requirement.privateLedger == (expectedPrivateLedgers.${service} or null)
    );
  requiredIdentityExists =
    item:
    item.record != { }
    && validIdentityRecord {
      service = item.service;
      node = item.hostName;
      record = item.record;
    }
    && (item.record.private.sopsPath or (item.requirement.privateLedger or null))
    == (item.requirement.privateLedger or (item.record.private.sopsPath or null));
  hostSecret =
    hostName: secretName:
    (nixosConfigurations.${hostName}.config.sops.secrets or { }).${secretName} or null;
  implementationChecks =
    pkgs.lib.flatten (
      pkgs.lib.mapAttrsToList
        (
          hostName: requiredServices:
          let
            hostConfig = nixosConfigurations.${hostName} or null;
            records = pkgs.lib.mapAttrs (service: _requirement: identityServices.${service}.${hostName} or { }) requiredServices;
            ipnsSecret = hostSecret hostName "cluster-identity-ipns-key";
            statusSecret = hostSecret hostName "cluster-identity-status-ipns-key";
            leaderUserSecret = hostSecret hostName "cluster-identity-leader-user-ssh";
          in
          pkgs.lib.optionals (hostConfig != null) (
            pkgs.lib.optional
              (
                requiredServices ? ipns-publisher
                && (records.ipns-publisher.private.sopsKey or null) != null
              )
              (
                ipnsSecret != null
                && ipnsSecret.key == records.ipns-publisher.private.sopsKey
              )
            ++ pkgs.lib.optional
              (
                requiredServices ? status-ipns
                && (records.status-ipns.private.sopsKey or null) != null
              )
              (
                statusSecret != null
                && statusSecret.key == records.status-ipns.private.sopsKey
              )
            ++ pkgs.lib.optional
              (
                requiredServices ? leader-user-ssh
                && (records.leader-user-ssh.private.sopsKey or null) != null
              )
              (
                leaderUserSecret != null
                && leaderUserSecret.key == records.leader-user-ssh.private.sopsKey
                && leaderUserSecret.path == records.leader-user-ssh.private.targetPath
              )
          )
        )
        (requirements.byHost or { })
    );
  valid =
    policy != { }
    && (requirements.schema or "") == "cluster.identity.requirements.v1"
    && requirements.byDendrite != { }
    && requirements.byHost != { }
    && pkgs.lib.all validDendriteRequirement dendriteRequirementRecords
    && pkgs.lib.all requiredIdentityExists requirementRecords
    && pkgs.lib.all (check: check) implementationChecks
    && builtins.isString (policy.clusterId or "")
    && policy.clusterId != ""
    && (identities.schema or "") == "cluster.identity.flake.v1"
    && identityServices != { }
    && pkgs.lib.all validIdentityRecord serviceRecords
    && hostAgeRecipients != { }
    && isSopsYaml (privateIdentityLedger.path or "")
    && isSopsYaml (hostAgePrivateLedger.path or "")
    && isAbsolute (registry.path or "")
    && isAbsolute (registry.materializedPath or "")
    && isAbsolute (registry.localStatePath or "")
    && registryRemotes != { }
    && builtins.isBool (transports.pubsub or null)
    && builtins.isBool (pubsub.enable or null)
    && builtins.isString (pubsub.topic or "")
    && pubsub.topic != ""
    && builtins.isInt (pubsub.maxHintAgeSeconds or null)
    && pubsub.maxHintAgeSeconds > 0
    && builtins.isInt (pubsub.maxFutureSkewSeconds or null)
    && pubsub.maxFutureSkewSeconds >= 0
    && builtins.isInt (pubsub.maxMessageBytes or null)
    && pubsub.maxMessageBytes > 0
    && builtins.isInt (pubsub.publishTimeoutSeconds or null)
    && pubsub.publishTimeoutSeconds > 0
    && builtins.isInt (pubsub.reconnectDelaySeconds or null)
    && pubsub.reconnectDelaySeconds > 0
    && pkgs.lib.all (
      remote:
      builtins.isString (remote.url or "")
      && remote.url != ""
      && builtins.isBool (remote.fetch or true)
      && builtins.isBool (remote.push or true)
    ) (builtins.attrValues registryRemotes)
    && leaders != { }
    && pkgs.lib.all (
      leader:
      builtins.isString (leader.publicSigningKey or "")
      && leader.publicSigningKey != ""
      && (
        (leader.signingKeyPath or null) == null
        || isAbsolute leader.signingKeyPath
      )
    ) (builtins.attrValues leaders)
    && isAbsolute (rules.signingKeyPath or "")
    && builtins.isBool (rules.allowPlaceholderSignatures or null)
    && builtins.isInt (rules.policyGeneration or null)
    && builtins.isBool (rules.burnedAlwaysWins or null)
    && builtins.isBool (rules.requireReceiptBeforePromote or null)
    && (rules.sameGenerationConflict or "") == "freeze-subject"
    && (rules.allowRollback or null) == false
    && builtins.isInt (thresholds.hostAgeRotation or null)
    && builtins.isInt (thresholds.leaderPolicyUpdate or null);
in
assert valid;
pkgs.runCommand "identity-policy" { } ''
  touch "$out"
''
