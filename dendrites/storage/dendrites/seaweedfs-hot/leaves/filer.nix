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
  filerPort = hotPool.filerPort or 8888;
  filerPath = hotPool.filerPath or "/srv/seaweedfs/filer";
  mountPoint = hotPool.mountPoint or "/hot";
  yggAddress = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "nodes"
    hostName
    "address"
  ] null site;
  bindAddr = if yggAddress != null then yggAddress else "127.0.0.1";
  filerEndpoint =
    if lib.hasInfix ":" bindAddr then
      "[${bindAddr}]:${toString filerPort}"
    else
      "${bindAddr}:${toString filerPort}";
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
  isFiler = builtins.elem "seaweed-filer" (hostInventory.roles or [ ]);
in
lib.mkIf isFiler {
  systemd.services.seaweedfs-filer = {
    description = "SeaweedFS filer server";
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
      ExecStartPre = "+${pkgs.writeShellScript "seaweedfs-filer-prestart" ''
        set -euo pipefail
        install -d -o seaweedfs -g seaweedfs -m 0750 ${filerPath}
        install -d -o seaweedfs -g seaweedfs -m 0750 ${filerPath}/filerldb2
      ''}";
      ExecStart = lib.concatStringsSep " " (
        [
          "${lib.getExe' pkgs.seaweedfs "weed"}"
          "filer"
          "-ip=${bindAddr}"
          "-port=${toString filerPort}"
          "-defaultStoreDir=${filerPath}"
        ]
        ++ lib.optionals (masterAddrs != "") [ "-master=${masterAddrs}" ]
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

  systemd.services.seaweedfs-hot-mount = {
    description = "SeaweedFS hot pool FUSE mount";
    wantedBy = [ "multi-user.target" ];
    requires = [ "seaweedfs-filer.service" ];
    after = [ "seaweedfs-filer.service" ];
    serviceConfig = {
      Type = "simple";
      ExecStartPre = [
        "+${pkgs.writeShellScript "seaweedfs-hot-mount-prestart" ''
          set -euo pipefail
          ${pkgs.util-linux}/bin/umount -l ${mountPoint} 2>/dev/null || true
          install -d -m 0777 ${mountPoint}
        ''}"
      ];
      ExecStart = lib.concatStringsSep " " [
        "${lib.getExe' pkgs.seaweedfs "weed"}"
        "mount"
        "-filer=${filerEndpoint}"
        "-dir=${mountPoint}"
        "-dirAutoCreate"
        "-umask=000"
      ];
      ExecStop = "-${pkgs.util-linux}/bin/umount -l ${mountPoint}";
      Restart = "on-failure";
      RestartSec = "5s";
    };
  };

  systemd.tmpfiles.rules = [
    "d ${filerPath}   0750 seaweedfs seaweedfs - -"
    "d ${mountPoint}  0777 root root - -"
  ];
}
