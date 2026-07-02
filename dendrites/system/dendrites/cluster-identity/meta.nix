{
  name = "system/cluster-identity";
  kind = "sub-dendrite";
  maturity = "experimental";
  provides = [
    "live-cluster-identity-registry"
    "cluster-identity-agent"
  ];
  requires = [ "system" ];
  conflicts = [ ];
  cheatsheets.fileRegex = "^cheats/.*\\.cheat$";
  identityRequirements = [
    {
      service = "host-age";
      generator = "host-age";
      sourceLedger = "inventory/keys/host-age-recipients.nix";
    }
    {
      service = "ssh-host";
      generator = "ssh-host";
      sourceLedger = "inventory/identity-services/ssh-host.nix";
    }
    {
      service = "ipns-publisher";
      generator = "ipns-publisher";
      sourceLedger = "inventory/identity-services/ipns-publisher.nix";
      privateLedger = "inventory/keys/leaders/leader-ipns-keys.sops.yaml";
      registryPublish = false;
      when = {
        path = [
          "org"
          "clusterIdentity"
          "role"
        ];
        equals = "leader";
      };
    }
    {
      service = "onion-mirror";
      generator = "onion-mirror";
      sourceLedger = "inventory/identity-services/onion-mirror.nix";
      registryPublish = false;
      when = {
        path = [
          "org"
          "clusterIdentity"
          "role"
        ];
        equals = "leader";
      };
    }
    {
      service = "status-ipns";
      generator = "status-ipns";
      sourceLedger = "inventory/identity-services/status-ipns.nix";
      privateLedger = "inventory/keys/identities/cluster-private-identities.sops.yaml";
    }
    {
      service = "leader-user-ssh";
      generator = "leader-user-ssh";
      sourceLedger = "inventory/identity-services/leader-user-ssh.nix";
      privateLedger = "inventory/keys/identities/cluster-private-identities.sops.yaml";
      registryPublish = false;
      when = {
        path = [
          "org"
          "clusterIdentity"
          "role"
        ];
        equals = "leader";
      };
    }
  ];
}
