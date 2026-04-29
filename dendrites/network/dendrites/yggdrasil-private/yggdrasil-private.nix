{
  config,
  hostName,
  hostInventory,
  lib,
  site,
  ...
}:
let
  privateYgg = lib.attrByPath [ "networks" "privateYggdrasil" ] { } site;
  transport = privateYgg.transport or { };
  firewallDefaults = privateYgg.firewall or { };
  defaults = privateYgg.defaults or { };
  nodes = privateYgg.nodes or { };
  hostNode = nodes.${hostName} or null;

  defaultScheme = transport.scheme or "tls";
  defaultPort = transport.port or 14742;
  firewallInterface = transport.interface or null;
  defaultIfName = defaults.ifName or "ygg0";
  defaultMulticastInterfaces = defaults.multicastInterfaces or [ ];
  defaultNodeInfoPrivacy = defaults.nodeInfoPrivacy or true;
  defaultPersistentKeys = defaults.persistentKeys or true;
  defaultOpenMulticastPort = defaults.openMulticastPort or false;
  hostDendrites = hostInventory.dendrites or [ ];
  hostFirewall = if hostNode == null then firewallDefaults else lib.recursiveUpdate firewallDefaults (hostNode.firewall or { });
  firewallEnforce = hostFirewall.enforce or true;
  firewallOverlay = hostFirewall.overlay or { };
  transportFirewall = hostFirewall.transport or { };
  openListenerFirewall = transportFirewall.openListener or transport.openFirewall or false;
  firewallCheckReversePath = hostFirewall.checkReversePath or true;

  peerHosts = if hostNode == null then [ ] else hostNode.peers or [ ];

  peerNode = peerHost: nodes.${peerHost} or { };

  peerUri = peerHost:
    let
      peer = peerNode peerHost;
      peerScheme = peer.scheme or defaultScheme;
      peerPort = peer.port or defaultPort;
      peerHostName = peer.endpointHost or peerHost;
      peerKey = peer.publicKey or null;
      peerKeySuffix = lib.optionalString (peerKey != null) "?key=${peerKey}";
    in
    peer.uri or "${peerScheme}://${peerHostName}:${toString peerPort}${peerKeySuffix}";

  peerKeys = lib.filter (key: key != null) (builtins.map (peerHost: (peerNode peerHost).publicKey or null) peerHosts);
  peerAddresses = lib.filter (address: address != null) (builtins.map (peerHost: (peerNode peerHost).address or null) peerHosts);
  missingPeerAddresses = builtins.filter (peerHost: ((peerNode peerHost).address or null) == null) peerHosts;
  missingPeerPublicKeys = builtins.filter (peerHost: ((peerNode peerHost).publicKey or null) == null) peerHosts;

  hostListenScheme = if hostNode == null then defaultScheme else hostNode.listenScheme or defaultScheme;
  hostListenPort = if hostNode == null then defaultPort else hostNode.listenPort or defaultPort;
  hostListenHost = if hostNode == null then "[::]" else hostNode.listenHost or "[::]";
  hostIfName = if hostNode == null then defaultIfName else hostNode.ifName or defaultIfName;
  hostMulticastInterfaces = if hostNode == null then defaultMulticastInterfaces else hostNode.multicastInterfaces or defaultMulticastInterfaces;
  hostNodeInfoPrivacy = if hostNode == null then defaultNodeInfoPrivacy else hostNode.nodeInfoPrivacy or defaultNodeInfoPrivacy;
  hostPersistentKeys = if hostNode == null then defaultPersistentKeys else hostNode.persistentKeys or defaultPersistentKeys;
  hostOpenMulticastPort = if hostNode == null then defaultOpenMulticastPort else hostNode.openMulticastPort or defaultOpenMulticastPort;
  hostListenEnabled = if hostNode == null then false else hostNode.listen or false;
  hostAllowlist = lib.unique (peerKeys ++ (if hostNode == null then [ ] else hostNode.extraAllowedPublicKeys or [ ]));
  hostOverlayAllowedTCPPorts = firewallOverlay.allowedTCPPorts or [ ];
  hostOverlayAllowedUDPPorts = firewallOverlay.allowedUDPPorts or [ ];
  hostOverlayRestrictToPeerSources = firewallOverlay.restrictToPeerSources or false;
  hostOverlayExtraAllowedSourceAddresses = firewallOverlay.extraAllowedSourceAddresses or [ ];
  hostOverlayAllowedSourceAddresses = lib.unique (peerAddresses ++ hostOverlayExtraAllowedSourceAddresses);
  firewallBackend = config.networking.firewall.backend or "iptables";

  listenerProtocol =
    {
      tcp = "tcp";
      tls = "tcp";
      ws = "tcp";
      wss = "tcp";
      quic = "udp";
    }
    .${hostListenScheme} or null;

  hostHasOverlayInterface = hostNode != null && hostIfName != "none";
  hostShouldOpenListenerFirewall = firewallEnforce && hostListenEnabled && openListenerFirewall && firewallInterface != null && listenerProtocol != null;
  hostTrustedInterfaces = config.networking.firewall.trustedInterfaces or [ ];

  yggFirewallInterfaces = lib.optionalAttrs (hostHasOverlayInterface && firewallEnforce) {
    "${hostIfName}" = {
      allowedTCPPorts = hostOverlayAllowedTCPPorts;
      allowedUDPPorts = hostOverlayAllowedUDPPorts;
    };
  };

  transportFirewallInterfaces = lib.optionalAttrs hostShouldOpenListenerFirewall {
    "${firewallInterface}" =
      if listenerProtocol == "udp" then
        {
          allowedUDPPorts = [ hostListenPort ];
        }
      else
        {
          allowedTCPPorts = [ hostListenPort ];
        };
  };

  yggHostEntries = builtins.listToAttrs (
    lib.concatMap
      (nodeName:
        let
          node = nodes.${nodeName};
          address = node.address or null;
          aliases = lib.unique ([ "${nodeName}-ygg" ] ++ (node.aliases or [ ]));
        in
        lib.optional (address != null) {
          name = address;
          value = aliases;
        })
      (builtins.attrNames nodes)
  );

  yggPeerSourceFilterCommands =
    if !(hostHasOverlayInterface && firewallEnforce && hostOverlayRestrictToPeerSources && firewallBackend == "iptables") then
      ""
    else
      let
        acceptRule = sourceAddress: ''
          ip6tables -w -I nixos-fw 1 -i ${lib.escapeShellArg hostIfName} -s ${lib.escapeShellArg sourceAddress} -j nixos-fw-accept
        '';
        dropRule = ''
          ip6tables -w -I nixos-fw 1 -i ${lib.escapeShellArg hostIfName} -j DROP
        '';
      in
      dropRule + lib.concatMapStrings acceptRule hostOverlayAllowedSourceAddresses;
in
{
  assertions = lib.optionals (hostNode != null && firewallEnforce) (
    [
      {
        assertion = config.networking.firewall.enable;
        message = "Host '${hostName}' enables network/yggdrasil-private but disables networking.firewall.enable; Yggdrasil overlay traffic is routable and must be protected by the host firewall.";
      }
    ]
    ++ lib.optionals hostHasOverlayInterface [
      {
        assertion = !(builtins.elem hostIfName hostTrustedInterfaces);
        message = "Host '${hostName}' enables network/yggdrasil-private but trusts firewall interface '${hostIfName}', which would bypass overlay service filtering.";
      }
    ]
    ++ lib.optionals hostShouldOpenListenerFirewall [
      {
        assertion = !(builtins.elem firewallInterface hostTrustedInterfaces);
        message = "Host '${hostName}' enables a private Yggdrasil listener on '${firewallInterface}' but also marks that interface as trusted, bypassing listener port filtering.";
      }
    ]
    ++ lib.optionals (hostHasOverlayInterface && hostOverlayRestrictToPeerSources) [
      {
        assertion = firewallBackend == "iptables";
        message = "Host '${hostName}' enables network/yggdrasil-private peer-source filtering on '${hostIfName}', but the current firewall backend '${firewallBackend}' is not yet supported for that mode.";
      }
      {
        assertion = missingPeerAddresses == [ ];
        message = "Host '${hostName}' enables network/yggdrasil-private peer-source filtering on '${hostIfName}' but peers are missing inventory.networks.privateYggdrasil.nodes.<peer>.address: ${lib.concatStringsSep ", " missingPeerAddresses}.";
      }
      {
        assertion = missingPeerPublicKeys == [ ];
        message = "Host '${hostName}' enables network/yggdrasil-private peer-source filtering on '${hostIfName}' but peers are missing inventory.networks.privateYggdrasil.nodes.<peer>.publicKey: ${lib.concatStringsSep ", " missingPeerPublicKeys}.";
      }
    ]
  );

  services.yggdrasil = {
    enable = hostNode != null;
    openMulticastPort = hostOpenMulticastPort;
    persistentKeys = hostPersistentKeys;
    settings = lib.mkIf (hostNode != null) {
      AllowedPublicKeys = hostAllowlist;
      IfName = hostIfName;
      Listen = lib.optional hostListenEnabled "${hostListenScheme}://${hostListenHost}:${toString hostListenPort}";
      MulticastInterfaces = hostMulticastInterfaces;
      NodeInfoPrivacy = hostNodeInfoPrivacy;
      Peers = builtins.map peerUri peerHosts;
    };
  };

  networking.firewall = lib.mkIf (hostNode != null && firewallEnforce) {
    enable = lib.mkDefault true;
    checkReversePath = lib.mkDefault firewallCheckReversePath;
    interfaces = lib.recursiveUpdate yggFirewallInterfaces transportFirewallInterfaces;
    extraCommands = lib.mkIf (yggPeerSourceFilterCommands != "") (lib.mkAfter yggPeerSourceFilterCommands);
  };

  networking.hosts = lib.mkIf (yggHostEntries != { }) yggHostEntries;
}
