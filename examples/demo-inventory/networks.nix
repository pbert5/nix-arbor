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

    defaults = {
      ifName = "ygg0";
      multicastInterfaces = [ ];
      nodeInfoPrivacy = true;
      openMulticastPort = false;
      persistentKeys = true;
    };

    firewall = {
      enforce = true;
      checkReversePath = true;
      transport.openListener = true;
      overlay = {
        allowedTCPPorts = [ ];
        allowedUDPPorts = [ ];
        restrictToPeerSources = false;
      };
    };

    nodes = {
      workstation-1 = {
        endpointHost = "workstation-1";
        listen = true;
        peers = [ "storage-1" ];
        aliases = [ "workstation-1-ygg" ];
        address = "200:db8::101";
        publicKey = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
      };

      storage-1 = {
        endpointHost = "storage-1";
        listen = true;
        peers = [ "workstation-1" ];
        aliases = [ "storage-1-ygg" ];
        address = "200:db8::102";
        publicKey = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
      };
    };
  };
}
