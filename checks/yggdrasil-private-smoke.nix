{ pkgs }:
let
  lib = pkgs.lib;
  site = {
    networks.privateYggdrasil = {
      transport = {
        scheme = "tcp";
        interface = "eth1";
        port = 14742;
        openFirewall = true;
      };

      firewall = {
        enforce = true;
        checkReversePath = true;
        transport.openListener = true;
        overlay.allowedTCPPorts = [ ];
      };

      defaults = {
        ifName = "ygg0";
        multicastInterfaces = [ ];
        nodeInfoPrivacy = true;
        openMulticastPort = false;
        persistentKeys = true;
      };

      nodes = {
        alpha = {
          endpointHost = "192.168.0.10";
          firewall.overlay.allowedTCPPorts = [ 18080 ];
          listen = true;
          listenHost = "0.0.0.0";
          peers = [ "beta" ];
        };

        beta = {
          endpointHost = "192.168.0.10";
          listen = true;
          listenHost = "0.0.0.0";
          peers = [ "alpha" ];
        };
      };
    };
  };

  mkNode =
    {
      hostName,
      address,
    }:
    {
      pkgs,
      ...
    }:
    {
      imports = [ ../dendrites/network/dendrites/yggdrasil-private/yggdrasil-private.nix ];

      _module.args.site = site;
      _module.args.hostName = hostName;
      _module.args.hostInventory = {
        dendrites = [ "network/yggdrasil-private" ];
      };

      environment.systemPackages = with pkgs; [
        curl
        iproute2
        python3
        yggdrasil
      ];

      networking = {
        hostName = hostName;
        interfaces.eth1.ipv4.addresses = [
          {
            inherit address;
            prefixLength = 24;
          }
        ];
        useDHCP = false;
      };

      system.stateVersion = "25.11";

      systemd.services.overlay-http-allowed = lib.mkIf (hostName == "alpha") {
        description = "HTTP server exposed through the private Ygg overlay";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          ExecStart = "${pkgs.python3}/bin/python -m http.server 18080 --bind ::";
          Restart = "always";
        };
      };

      systemd.services.overlay-http-denied = lib.mkIf (hostName == "alpha") {
        description = "HTTP server intentionally blocked by the private Ygg firewall";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          ExecStart = "${pkgs.python3}/bin/python -m http.server 18081 --bind ::";
          Restart = "always";
        };
      };
    };
in
pkgs.testers.runNixOSTest {
  name = "yggdrasil-private-smoke";

  nodes = {
    alpha = mkNode {
      hostName = "alpha";
      address = "192.168.0.10";
    };

    beta = mkNode {
      hostName = "beta";
      address = "192.168.0.10";
    };
  };

  testScript = ''
    start_all()

    alpha.wait_for_unit("multi-user.target")
    beta.wait_for_unit("multi-user.target")

    alpha.wait_for_unit("yggdrasil.service")
    beta.wait_for_unit("yggdrasil.service")
    alpha.wait_for_unit("overlay-http-allowed.service")
    alpha.wait_for_unit("overlay-http-denied.service")

    alpha.wait_until_succeeds("ip link show ygg0")
    beta.wait_until_succeeds("ip link show ygg0")

    alpha.wait_until_succeeds("yggdrasilctl getPeers | grep -q 192.168.0.10")
    beta.wait_until_succeeds("yggdrasilctl getPeers | grep -q 192.168.0.10")

    alpha_ygg = alpha.succeed("ip -6 addr show dev ygg0 | awk '/inet6 2/{sub(/\\/.*$/, \"\", $2); print $2; exit}'").strip()

    beta.wait_until_succeeds(f"${pkgs.curl}/bin/curl --fail --silent --max-time 5 http://[{alpha_ygg}]:18080")
    beta.fail(f"${pkgs.curl}/bin/curl --fail --silent --max-time 5 http://[{alpha_ygg}]:18081")
  '';
}
