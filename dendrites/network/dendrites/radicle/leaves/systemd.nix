{
  lib,
  pkgs,
  site,
  hostInventory,
  hostName,
  ...
}:
let
  radicleOrg = lib.attrByPath [ "org" "network" "radicle" ] { } hostInventory;
  yggAddress = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "nodes"
    hostName
    "address"
  ] null site;
  nodePort = radicleOrg.port or (lib.attrByPath [ "ports" "radicleNode" "port" ] 8776 site);
  yggIfName = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "defaults"
    "ifName"
  ] "ygg0" site;
  identityRequirement = lib.attrByPath [
    "identityRequirements"
    "byHost"
    hostName
    "radicle"
  ] { } site;
  privateKeyFile = radicleOrg.privateKeyFile or identityRequirement.targetPath or null;
  radHome =
    if privateKeyFile == null then
      "/var/lib/radicle"
    else
      builtins.dirOf (builtins.dirOf privateKeyFile);
  isSeed = radicleOrg.seed or false;
  serviceEnabled = privateKeyFile != null;
  # Raw bind address (IPv6 Ygg or loopback fallback).
  bindAddr = if yggAddress != null then yggAddress else "127.0.0.1";
  # Socket address: IPv6 addresses need brackets, IPv4/loopback do not.
  listenAddr =
    if yggAddress != null then
      "[${bindAddr}]:${toString nodePort}"
    else
      "${bindAddr}:${toString nodePort}";
in
{
  # Disable the upstream NixOS radicle module — it requires publicKey to be
  # known at eval time but ours is generated on first boot. We manage the
  # service directly below.
  disabledModules = [ "services/misc/radicle.nix" ];

  assertions = [
    {
      assertion = !isSeed || privateKeyFile != null;
      message = ''
        Host "${hostName}" enables org.network.radicle.seed but
        the Radicle identity requirement has no targetPath.
        Declare the default destination in network/radicle meta.nix, or set
        org.network.radicle.privateKeyFile for an explicit custom key.
      '';
    }
  ];

  # Manage Radicle as a plain systemd service. The key destination normally
  # comes from the dendrite's identity requirement metadata.
  systemd.services.radicle-seed = lib.mkIf serviceEnabled {
    description = "Radicle seed node (cluster fabric)";
    wantedBy = [ "multi-user.target" ];
    after = [
      "network-online.target"
      "radicle-keygen.service"
    ];
    wants = [ "network-online.target" ];
    requires = [ "radicle-keygen.service" ];
    environment = {
      RAD_HOME = radHome;
      GIT_AUTHOR_EMAIL = "radicle@${hostName}";
    };
    preStart = ''
      if [ -S ${radHome}/node/control.sock ] \
        && ! ${pkgs.procps}/bin/pgrep -u radicle -x radicle-node >/dev/null; then
        rm -f ${radHome}/node/control.sock
      fi
    '';
    serviceConfig = {
      ExecStart = lib.concatStringsSep " " [
        "${lib.getExe' pkgs.radicle-node "radicle-node"}"
        "--listen"
        listenAddr
      ];
      Restart = "on-failure";
      RestartSec = "5s";
      User = "radicle";
      Group = "radicle";
      PrivateTmp = true;
      ProtectSystem = "strict";
      ReadWritePaths = [ radHome ];
      NoNewPrivileges = true;
    };
  };

  users.groups.radicle = lib.mkIf serviceEnabled { };
  users.users.radicle = lib.mkIf serviceEnabled {
    isSystemUser = true;
    group = "radicle";
    description = "Radicle service account";
    home = radHome;
    createHome = true;
  };

  # Open Radicle port only on the private overlay interface.
  networking.firewall.interfaces.${yggIfName}.allowedTCPPorts = lib.mkIf serviceEnabled [ nodePort ];
}
