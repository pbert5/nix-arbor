let
  identities = import ./private-yggdrasil-identities.nix;
  withIdentity = nodeName: node:
    node // (identities.${nodeName} or { });
in
{
  tailscale = {
    dendrite = "network/tailscale";
  };

  privateYggdrasil = {
    dendrite = "network/yggdrasil-private";
    public = false;

    transport = {
      scheme = "tls";
      interface = "tailscale0";
      port = 14742;
      openFirewall = true;
    };

    firewall = {
      enforce = true;
      checkReversePath = true;

      transport = {
        openListener = true;
      };

      overlay = {
        allowedTCPPorts = [ ];
        allowedUDPPorts = [ ];
        restrictToPeerSources = false;
      };
    };

    defaults = {
      ifName = "ygg0";
      multicastInterfaces = [ ];
      nodeInfoPrivacy = true;
      openMulticastPort = false;
      persistentKeys = true;
    };

    nodes = {
      dev-machine = withIdentity "dev-machine" {
        endpointHost = "dev-machine";
        listen = true;
        peers = [
          "r640-0"
          "desktoptoodle"
        ];
        aliases = [ "dev-machine-ygg" ];
      };

      "r640-0" = withIdentity "r640-0" {
        endpointHost = "r640-0";
        listen = true;
        peers = [
          "dev-machine"
          "desktoptoodle"
        ];
        aliases = [ "r640-0-ygg" ];
      };

      desktoptoodle = withIdentity "desktoptoodle" {
        endpointHost = "desktoptoodle";
        listen = true;
        peers = [
          "dev-machine"
          "r640-0"
        ];
        aliases = [ "desktoptoodle-ygg" ];
      };

      compute-worker = withIdentity "compute-worker" {
        endpointHost = "compute-worker";
        listen = false;
        peers = [ "dev-machine" ];
        aliases = [ "compute-worker-ygg" ];
      };
    };
  };
}
