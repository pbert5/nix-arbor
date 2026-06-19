{ pkgs, inventory }:
let
  identities = inventory.identities or { };
  policy = inventory.identityPolicy or { };
  registry = policy.registry or { };
  registryRemotes = registry.remotes or { };
  leaders = policy.leaders or { };
  rules = policy.policy or { };
  identityServices = identities.services or { };
  hostAgeRecipients = identities.encryption.hostAge.recipients or { };
  privateIdentityLedger = identities.encryption.privateIdentityLedger or { };
  hostAgePrivateLedger = identities.encryption.hostAgePrivateLedger or { };
  isAbsolute = value: builtins.isString value && builtins.substring 0 1 value == "/";
  isSopsYaml = value: builtins.isString value && builtins.match ".*\\.sops\\.ya?ml" value != null;
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
  valid =
    policy != { }
    && (identities.schema or "") == "cluster.identity.flake.v1"
    && identityServices != { }
    && pkgs.lib.all validIdentityRecord serviceRecords
    && hostAgeRecipients != { }
    && isSopsYaml (privateIdentityLedger.path or "")
    && isSopsYaml (hostAgePrivateLedger.path or "")
    && isAbsolute (registry.path or "")
    && isAbsolute (registry.materializedPath or "")
    && registryRemotes != { }
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
    && builtins.isInt (rules.leaderPolicyEpoch or null)
    && builtins.isBool (rules.burnedAlwaysWins or null)
    && builtins.isBool (rules.requireReceiptBeforePromote or null);
in
assert valid;
pkgs.runCommand "identity-policy" { } ''
  touch "$out"
''
