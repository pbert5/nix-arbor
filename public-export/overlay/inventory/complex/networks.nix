{
  layers = {
    public = {
      options = {
        visibility = "public";
        serviceExposure = "forbidden-by-default";
      };
      layers = {
        intraLan.networks.publicLanDhcp = {
          enabled = false;
          type = "dhcp";
          dendrite = null;
          description = "Planned public-side physical LAN DHCP surface.";
        };
        interLan = {
          options.serviceExposure = "peering-only";
          networks.publicYggdrasilPeering = {
            enabled = true;
            type = "yggdrasil-peering";
            dendrite = "network/yggdrasil-public-peering";
            description = "Public no-TUN Yggdrasil sidecar used only for LAN bridging and peer discovery.";
            policy = {
              exposeServices = false;
              peeringOnly = true;
            };
            transport = {
              scheme = "tls";
              interface = "tailscale0";
              port = 14743;
              openFirewall = true;
            };
            firewall = {
              openListener = true;
              checkReversePath = true;
            };
            defaults = {
              ifName = "none";
              multicastInterfaces = [ ];
              nodeInfoPrivacy = true;
              stateDir = "/var/lib/yggdrasil-public-peering";
            };
            extraPeers = [ ];
            nodes = {
              workstation-1 = {
                endpointHost = "workstation-1";
                listen = true;
                peers = [
                  "storage-1"
                  "library-1"
                ];
              };

              storage-1 = {
                endpointHost = "storage-1";
                listen = true;
                peers = [
                  "workstation-1"
                  "library-1"
                ];
              };

              library-1 = {
                endpointHost = "library-1";
                listen = true;
                peers = [
                  "workstation-1"
                  "storage-1"
                ];
              };
            };
          };
        };
      };
    };

    private = {
      options = {
        visibility = "private";
        serviceExposure = "explicit-allowlist";
      };
      layers = {
        intraLan.networks.privateLanDhcp = {
          enabled = false;
          type = "dhcp";
          dendrite = null;
          description = "Planned private physical LAN DHCP surface.";
        };
        interLan.networks = {
          tailscale = {
            enabled = true;
            type = "tailscale";
            dendrite = "network/tailscale";
          };

          privateYggdrasil = {
            enabled = true;
            type = "yggdrasil-overlay";
            dendrite = "network/yggdrasil-private";
            public = false;
            underlayNetwork = "publicYggdrasilPeering";

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
                peers = [
                  "storage-1"
                  "library-1"
                ];
                aliases = [ "workstation-1-ygg" ];
                address = "200:db8::101";
                publicKey = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
              };

              storage-1 = {
                endpointHost = "storage-1";
                listen = true;
                peers = [
                  "workstation-1"
                  "library-1"
                ];
                aliases = [ "storage-1-ygg" ];
                address = "200:db8::102";
                publicKey = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
              };

              library-1 = {
                endpointHost = "library-1";
                listen = true;
                peers = [
                  "workstation-1"
                  "storage-1"
                ];
                aliases = [ "library-1-ygg" ];
                address = "200:db8::103";
                publicKey = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc";
              };
            };
          };
        };
      };
    };
  };
}
