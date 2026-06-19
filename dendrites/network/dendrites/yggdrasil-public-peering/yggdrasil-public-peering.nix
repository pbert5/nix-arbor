{
  config,
  hostName,
  lib,
  pkgs,
  site,
  ...
}:
let
  network = lib.attrByPath [ "networks" "publicYggdrasilPeering" ] { } site;
  defaults = network.defaults or { };
  transport = network.transport or { };
  firewall = network.firewall or { };
  nodes = network.nodes or { };
  hostNode = nodes.${hostName} or null;

  stateDir = defaults.stateDir or "/var/lib/yggdrasil-public-peering";
  privateKeyFile = defaults.privateKeyFile or "${stateDir}/private.key";
  configFile = "/run/yggdrasil-public-peering/config.json";

  defaultScheme = transport.scheme or "tls";
  defaultPort = transport.port or 14743;
  firewallInterface = transport.interface or null;
  openListenerFirewall = firewall.openListener or transport.openFirewall or false;
  checkReversePath = firewall.checkReversePath or true;

  hostListenEnabled = if hostNode == null then false else hostNode.listen or false;
  hostListenScheme =
    if hostNode == null then defaultScheme else hostNode.listenScheme or defaultScheme;
  hostListenPort = if hostNode == null then defaultPort else hostNode.listenPort or defaultPort;
  hostListenHost = if hostNode == null then "[::]" else hostNode.listenHost or "[::]";
  hostPeerNames = if hostNode == null then [ ] else hostNode.peers or [ ];
  extraPeers = hostNode.extraPeers or network.extraPeers or [ ];
  extraAllowedPublicKeys = hostNode.extraAllowedPublicKeys or [ ];
  trustedInterfaces = config.networking.firewall.trustedInterfaces or [ ];

  peerNode = peerName: nodes.${peerName} or { };
  peerUri =
    peerName:
    let
      peer = peerNode peerName;
      peerScheme = peer.scheme or defaultScheme;
      peerPort = peer.port or defaultPort;
      peerHostName = peer.endpointHost or peerName;
      peerKey = peer.publicKey or null;
      peerKeySuffix = lib.optionalString (peerKey != null) "?key=${peerKey}";
    in
    peer.uri or "${peerScheme}://${peerHostName}:${toString peerPort}${peerKeySuffix}";
  peerPublicKeys = lib.filter (key: key != null) (
    builtins.map (peerName: (peerNode peerName).publicKey or null) hostPeerNames
  );

  listenUris = lib.optional hostListenEnabled "${hostListenScheme}://${hostListenHost}:${toString hostListenPort}";
  peerUris = (builtins.map peerUri hostPeerNames) ++ extraPeers;
  allowedPublicKeys = lib.unique (peerPublicKeys ++ extraAllowedPublicKeys);

  listenerProtocol =
    {
      tcp = "tcp";
      tls = "tcp";
      ws = "tcp";
      wss = "tcp";
      quic = "udp";
    }
    .${hostListenScheme} or null;

  shouldOpenListenerFirewall =
    hostNode != null
    && hostListenEnabled
    && openListenerFirewall
    && firewallInterface != null
    && listenerProtocol != null;

  configTemplate = pkgs.writeText "yggdrasil-public-peering-template.json" (
    builtins.toJSON {
      PrivateKey = "@PRIVATE_KEY@";
      AdminListen = "none";
      Peers = peerUris;
      InterfacePeers = { };
      Listen = listenUris;
      MulticastInterfaces = defaults.multicastInterfaces or [ ];
      AllowedPublicKeys = allowedPublicKeys;
      IfName = "none";
      IfMTU = defaults.ifMTU or 65535;
      NodeInfoPrivacy = defaults.nodeInfoPrivacy or true;
      NodeInfo = null;
    }
  );

  renderConfig = pkgs.writeShellScript "render-yggdrasil-public-peering-config" ''
    set -euo pipefail
    install -d -m 0700 ${lib.escapeShellArg stateDir}
    install -d -m 0755 "$(dirname ${lib.escapeShellArg configFile})"

    if [ ! -s ${lib.escapeShellArg privateKeyFile} ]; then
      umask 077
      ${lib.getExe' pkgs.yggdrasil "yggdrasil"} -genconf -json \
        | ${lib.getExe pkgs.jq} -r .PrivateKey \
        > ${lib.escapeShellArg privateKeyFile}
    fi

    private_key="$(cat ${lib.escapeShellArg privateKeyFile})"
    ${lib.getExe pkgs.jq} --arg private_key "$private_key" \
      '.PrivateKey = $private_key' \
      ${lib.escapeShellArg configTemplate} \
      > ${lib.escapeShellArg configFile}
    chmod 0600 ${lib.escapeShellArg configFile}
  '';
in
{
  assertions =
    lib.optionals (hostNode != null) [
      {
        assertion = (defaults.ifName or "none") == "none";
        message = "network/yggdrasil-public-peering must keep IfName = \"none\"; public peering must not create a routable service interface.";
      }
    ]
    ++ lib.optionals shouldOpenListenerFirewall [
      {
        assertion = !(builtins.elem firewallInterface trustedInterfaces);
        message = "Host '${hostName}' enables public Yggdrasil peering on '${firewallInterface}' but also marks that interface as trusted.";
      }
    ];

  systemd.services.yggdrasil-public-peering = lib.mkIf (hostNode != null) {
    description = "Public inter-LAN Yggdrasil peering sidecar";
    wantedBy = [ "multi-user.target" ];
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    preStart = "${renderConfig}";
    serviceConfig = {
      ExecStart = "${lib.getExe' pkgs.yggdrasil "yggdrasil"} -useconffile ${configFile}";
      Restart = "on-failure";
      RestartSec = "5s";
      StateDirectory = "yggdrasil-public-peering";
      RuntimeDirectory = "yggdrasil-public-peering";
      DynamicUser = false;
      User = "root";
      Group = "root";
      NoNewPrivileges = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      ReadWritePaths = [
        stateDir
        "/run/yggdrasil-public-peering"
      ];
      RestrictAddressFamilies = [
        "AF_UNIX"
        "AF_INET"
        "AF_INET6"
        "AF_NETLINK"
      ];
    };
  };

  networking.firewall = lib.mkIf shouldOpenListenerFirewall {
    enable = lib.mkDefault true;
    checkReversePath = lib.mkDefault checkReversePath;
    interfaces.${firewallInterface} =
      if listenerProtocol == "udp" then
        { allowedUDPPorts = [ hostListenPort ]; }
      else
        { allowedTCPPorts = [ hostListenPort ]; };
  };
}
