{ ... }:
{
  # The key is provisioned by the operator; its contents must never enter
  # this flake or the Nix store.
  arbor.environment.public.sshHosts.eVolver = {
    hostname = "200:c739:8dc3:8e5a:b1b4:bf7b:1142:d29a";
    user = "root";
    identityFile = [ "/home/ash/.ssh/cluster-leader-ed25519" ];
    extraOptions = {
      IdentitiesOnly = "yes";
    };
  };
}
