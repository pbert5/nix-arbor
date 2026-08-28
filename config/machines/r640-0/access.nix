{ ... }:
{
  # The key is provisioned by the operator; its contents must never enter
  # this flake or the Nix store.
  arbor.environment.public.sshHosts.eVolver = {
    # Tailscale MagicDNS is the reachable stable route from r640-0. The
    # desktoptoodle operator path continues to use the Yggdrasil endpoint.
    hostname = "evolver";
    user = "root";
    identityFile = [ "/home/ash/.ssh/cluster-leader-ed25519" ];
    extraOptions = {
      IdentitiesOnly = "yes";
    };
  };
}
