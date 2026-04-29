{ pkgs }:
let
  lib = pkgs.lib;
  system = pkgs.stdenv.hostPlatform.system;
  evalConfig = import "${pkgs.path}/nixos/lib/eval-config.nix";
  helpers = import ../lib/helpers.nix { inherit lib; };
  inventoryLib = import ../lib/inventory.nix {
    inherit helpers lib;
  };

  inventory = inventoryLib.normalizeInventory (import ../inventory/inventory.nix { });

  site = {
    networks.privateYggdrasil = {
      transport = {
        scheme = "tls";
        interface = "tailscale0";
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
          address = "200:1111:2222:3333::1";
          aliases = [ "alpha-overlay" ];
          endpointHost = "alpha.example.test";
          publicKey = "alpha-public-key";
          firewall.overlay.allowedTCPPorts = [ 18080 ];
          firewall.overlay.restrictToPeerSources = true;
          listen = true;
          peers = [ "beta" ];
        };

        beta = {
          address = "200:1111:2222:3333::2";
          aliases = [ "beta-overlay" ];
          endpointHost = "beta.example.test";
          publicKey = "beta-public-key";
          firewall.overlay.restrictToPeerSources = true;
          listen = false;
          peers = [ "alpha" ];
        };
      };
    };
  };

  mkEval =
    {
      hostName,
      hostInventory,
      modules ? [ ],
    }:
    evalConfig {
      inherit system;
      modules =
        modules
        ++ [
          ../dendrites/network/dendrites/yggdrasil-private/yggdrasil-private.nix
          {
            _module.args.site = site;
            _module.args.hostName = hostName;
            _module.args.hostInventory = hostInventory;

            system.stateVersion = "25.11";
          }
        ];
    };

  alphaEval = mkEval {
    hostName = "alpha";
    hostInventory.dendrites = [
      "network/tailscale"
      "network/yggdrasil-private"
    ];
    modules = [ ../dendrites/network/dendrites/tailscale/tailscale.nix ];
  };

  betaEval = mkEval {
    hostName = "beta";
    hostInventory.dendrites = [ "network/yggdrasil-private" ];
  };

  alphaAliases = lib.attrByPath [ "networking" "hosts" "200:1111:2222:3333::1" ] [ ] alphaEval.config;
  betaAliases = lib.attrByPath [ "networking" "hosts" "200:1111:2222:3333::2" ] [ ] betaEval.config;

  trustedOverlayEval = builtins.tryEval (
    (mkEval {
      hostName = "alpha";
      hostInventory.dendrites = [ "network/yggdrasil-private" ];
      modules = [
        {
          networking.firewall.trustedInterfaces = [ "ygg0" ];
        }
      ];
    }).config.system.build.toplevel
  );

  trustedTransportEval = builtins.tryEval (
    (mkEval {
      hostName = "alpha";
      hostInventory.dendrites = [
        "network/tailscale"
        "network/yggdrasil-private"
      ];
      modules = [
        ../dendrites/network/dendrites/tailscale/tailscale.nix
        {
          networking.firewall.trustedInterfaces = [ "tailscale0" ];
        }
      ];
    }).config.system.build.toplevel
  );

  assertionsHold =
    assert builtins.elem "network/yggdrasil-private" inventory.hosts.dev-machine.dendrites;
    assert builtins.elem "network/tailscale" inventory.hosts.dev-machine.dendrites;
    assert builtins.elem "network/yggdrasil-private" inventory.hosts.compute-worker.dendrites;
    assert !(builtins.elem "network/tailscale" inventory.hosts.compute-worker.dendrites);
    assert alphaEval.config.networking.firewall.enable;
    assert alphaEval.config.networking.firewall.checkReversePath == true;
    assert alphaEval.config.services.tailscale.enable;
    assert alphaEval.config.services.yggdrasil.enable;
    assert alphaEval.config.services.yggdrasil.settings.AllowedPublicKeys == [ "beta-public-key" ];
    assert alphaEval.config.services.yggdrasil.settings.IfName == "ygg0";
    assert alphaEval.config.services.yggdrasil.settings.Listen == [ "tls://[::]:14742" ];
    assert alphaEval.config.services.yggdrasil.settings.Peers == [ "tls://beta.example.test:14742?key=beta-public-key" ];
    assert builtins.elem 14742 alphaEval.config.networking.firewall.interfaces.tailscale0.allowedTCPPorts;
    assert alphaEval.config.networking.firewall.interfaces.ygg0.allowedTCPPorts == [ 18080 ];
    assert alphaEval.config.networking.firewall.interfaces.ygg0.allowedUDPPorts == [ ];
    assert lib.hasInfix "DROP" alphaEval.config.networking.firewall.extraCommands;
    assert lib.hasInfix "200:1111:2222:3333::2" alphaEval.config.networking.firewall.extraCommands;
    assert builtins.elem "alpha-ygg" alphaAliases;
    assert builtins.elem "alpha-overlay" alphaAliases;
    assert betaEval.config.services.yggdrasil.enable;
    assert betaEval.config.services.yggdrasil.settings.AllowedPublicKeys == [ "alpha-public-key" ];
    assert betaEval.config.services.yggdrasil.settings.Listen == [ ];
    assert betaEval.config.services.yggdrasil.settings.Peers == [ "tls://alpha.example.test:14742?key=alpha-public-key" ];
    assert betaEval.config.networking.firewall.enable;
    assert betaEval.config.networking.firewall.interfaces.ygg0.allowedTCPPorts == [ ];
    assert betaEval.config.networking.firewall.interfaces.ygg0.allowedUDPPorts == [ ];
    assert lib.hasInfix "DROP" betaEval.config.networking.firewall.extraCommands;
    assert lib.hasInfix "200:1111:2222:3333::1" betaEval.config.networking.firewall.extraCommands;
    assert (lib.attrByPath [ "networking" "firewall" "interfaces" "tailscale0" "allowedTCPPorts" ] [ ] betaEval.config) == [ ];
    assert builtins.elem "beta-ygg" betaAliases;
    assert builtins.elem "beta-overlay" betaAliases;
    assert trustedOverlayEval.success == false;
    assert trustedTransportEval.success == false;
    true;
in
assert assertionsHold;
pkgs.runCommand "network-overlay-eval" { } ''
  touch "$out"
''
