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
  volumePort = hotPool.volumePort or 8080;
  volumePath = hotPool.volumePath or "/srv/seaweedfs/volumes";
  yggAddress = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "nodes"
    hostName
    "address"
  ] null site;
  bindAddr = if yggAddress != null then yggAddress else "127.0.0.1";
  # Master addresses for this volume node to register with.
  # Populated from all hosts that carry the seaweed-master role.
  masterHosts = lib.filter (
    h: builtins.elem "seaweed-master" ((site.hosts or { }).${h}.roles or [ ])
  ) (builtins.attrNames (site.hosts or { }));
  masterPort = hotPool.masterPort or 9333;
  masterAddrs = lib.concatMapStringsSep "," (
    h:
    let
      addr = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" h "address" ] h site;
    in
    "${addr}:${toString masterPort}"
  ) masterHosts;
  isVolume = builtins.elem "seaweed-volume" (hostInventory.roles or [ ]);
in
lib.mkIf isVolume {
  systemd.services.seaweedfs-volume = {
    description = "SeaweedFS volume server";
    wantedBy = [ "multi-user.target" ];
    after = [
      "network-online.target"
      "systemd-tmpfiles-resetup.service"
      "seaweedfs-master.service"
    ];
    wants = [
      "network-online.target"
      "systemd-tmpfiles-resetup.service"
    ];
    serviceConfig = {
      ExecStartPre = "+${pkgs.writeShellScript "seaweedfs-volume-prestart" ''
        set -euo pipefail
        install -d -o seaweedfs -g seaweedfs -m 0750 ${volumePath}
      ''}";
      ExecStart = lib.concatStringsSep " " (
        [
          "${lib.getExe' pkgs.seaweedfs "weed"}"
          "volume"
          "-ip=${bindAddr}"
          "-port=${toString volumePort}"
          "-dir=${volumePath}"
        ]
        ++ lib.optionals (masterAddrs != "") [ "-mserver=${masterAddrs}" ]
      );
      Restart = "on-failure";
      RestartSec = "5s";
      User = "seaweedfs";
      Group = "seaweedfs";
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
    "d ${volumePath} 0750 seaweedfs seaweedfs - -"
  ];
}
