{
  lib,
  pkgs,
  site,
  hostInventory,
  hostName,
  ...
}:
let
  fabric = site.storageFabric or { };
  hotPool = lib.attrByPath [ "seaweedfs" "hotPool" ] { } fabric;
  masterPort = hotPool.masterPort or 9333;
  replication = hotPool.replication or "001";
  # Resolve the host's private Ygg address to use as bind address.
  yggAddress = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "nodes"
    hostName
    "address"
  ] null site;
  bindAddr = if yggAddress != null then yggAddress else "127.0.0.1";
  isMaster = builtins.elem "seaweed-master" (hostInventory.roles or [ ]);
in
lib.mkIf isMaster {
  systemd.services.seaweedfs-master = {
    description = "SeaweedFS master server";
    wantedBy = [ "multi-user.target" ];
    wants = [
      "network-online.target"
      "systemd-tmpfiles-resetup.service"
    ];
    after = [
      "network-online.target"
      "systemd-tmpfiles-resetup.service"
    ];
    serviceConfig = {
      ExecStartPre = "+${pkgs.writeShellScript "seaweedfs-master-prestart" ''
        set -euo pipefail
        install -d -o seaweedfs -g seaweedfs -m 0750 /srv/seaweedfs/master
      ''}";
      ExecStart = lib.concatStringsSep " " [
        "${lib.getExe' pkgs.seaweedfs "weed"}"
        "master"
        "-ip=${bindAddr}"
        "-port=${toString masterPort}"
        "-defaultReplication=${replication}"
        "-mdir=/srv/seaweedfs/master"
      ];
      Restart = "on-failure";
      RestartSec = "5s";
      User = "seaweedfs";
      Group = "seaweedfs";
      # Systemd hardening
      PrivateTmp = true;
      ProtectSystem = "full";
      ProtectHome = true;
      ProtectKernelTunables = true;
      ProtectKernelModules = true;
      ProtectKernelLogs = true;
      ProtectControlGroups = true;
      NoNewPrivileges = true;
      RestrictRealtime = true;
      RestrictSUIDSGID = true;
      LockPersonality = true;
      SystemCallArchitectures = "native";
      RestrictAddressFamilies = [
        "AF_UNIX"
        "AF_INET"
        "AF_INET6"
      ];
    };
  };

  systemd.tmpfiles.rules = [
    "d /srv/seaweedfs/master 0750 seaweedfs seaweedfs - -"
  ];
}
