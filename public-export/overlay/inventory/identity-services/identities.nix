let
  hostAgeRecipients = {
    "workstation-1" = {
      publicKey = "age1exampleexampleexampleexampleexampleexampleexampleexamplex";
      keyType = "age-x25519";
      privateKeyPath = "/var/lib/cluster-identity/age/host.agekey";
      enrolledAt = "2026-01-01T00:00:00Z";
      enrollment = "root-ssh";
    };

    "storage-1" = {
      publicKey = "age1exampleexampleexampleexampleexampleexampleexampleexampley";
      keyType = "age-x25519";
      privateKeyPath = "/var/lib/cluster-identity/age/host.agekey";
      enrolledAt = "2026-01-01T00:00:00Z";
      enrollment = "root-ssh";
    };
  };
  yggdrasilServices = import ./yggdrasil.nix;
  sshHostServices = import ./ssh-host.nix;
  radicleServices = import ./radicle.nix;
  gitAnnexServices = import ./git-annex.nix;
in
{
  schema = "cluster.identity.flake.v1";
  updatedAt = "2026-01-01T00:00:00Z";

  model = {
    sourceOfTruth = "flake";
    registryRole = "live-projection";
    defaultPublisher = "clusterctl identity publish";
  };

  encryption = {
    hostAge = {
      keyType = "age-x25519";
      privateKeyPath = "/var/lib/cluster-identity/age/host.agekey";
      recipients = hostAgeRecipients;
    };

    privateIdentityLedger = {
      status = "sops-nix";
      path = "inventory/keys/identities/cluster-private-identities.sops.yaml";
      encryptedTo = "leader host-age recipients";
      notes = "Private service keys live in a SOPS-encrypted flake file. Registry events carry delivery metadata, not plaintext private material.";
    };

    hostAgePrivateLedger = {
      status = "sops-nix";
      path = "inventory/keys/followers/host-age-private-keys.sops.yaml";
      encryptedTo = "leader host-age recipients";
      bootstrapTargetPath = "/var/lib/cluster-identity/age/host.agekey";
      notes = "This ledger is the leader-only recovery record for each host's base age key. The SSH bootstrap path may install exactly this key and no service identities.";
    };
  };

  services = {
    host-age = builtins.mapAttrs (_hostName: entry: {
      generation = 1;
      state = "active";
      sourceTimestamp = entry.enrolledAt;
      public = {
        ageRecipient = entry.publicKey;
        keyType = entry.keyType;
        privateKeyPath = entry.privateKeyPath;
      };
    }) hostAgeRecipients;

    yggdrasil = yggdrasilServices;
    ssh-host = sshHostServices;
    radicle = radicleServices;
    git-annex = gitAnnexServices;
  };
}
