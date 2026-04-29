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
  s3Port = hotPool.s3Port or 8333;
  s3Enable = lib.attrByPath [ "s3" "enable" ] false hotPool;
  yggAddress = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "nodes"
    hostName
    "address"
  ] null site;
  bindAddr = if yggAddress != null then yggAddress else "127.0.0.1";
  filerHosts = lib.filter (h: builtins.elem "seaweed-filer" ((site.hosts or { }).${h}.roles or [ ])) (
    builtins.attrNames (site.hosts or { })
  );
  filerPort = hotPool.filerPort or 8888;
  filerAddr = lib.optionalString (filerHosts != [ ]) (
    let
      h = builtins.head filerHosts;
      addr = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" h "address" ] h site;
    in
    "${addr}:${toString filerPort}"
  );
  isS3 = builtins.elem "seaweed-s3" (hostInventory.roles or [ ]);
in
lib.mkIf (isS3 && s3Enable) {
  systemd.services.seaweedfs-s3 = {
    description = "SeaweedFS S3 gateway";
    wantedBy = [ "multi-user.target" ];
    after = [
      "network-online.target"
      "seaweedfs-filer.service"
    ];
    wants = [ "network-online.target" ];
    serviceConfig = {
      ExecStart = lib.concatStringsSep " " (
        [
          "${lib.getExe' pkgs.seaweedfs "weed"}"
          "s3"
          "-ip=${bindAddr}"
          "-port=${toString s3Port}"
        ]
        ++ lib.optionals (filerAddr != "") [ "-filer=${filerAddr}" ]
      );
      Restart = "on-failure";
      RestartSec = "5s";
      User = "seaweedfs";
      Group = "seaweedfs";
      PrivateTmp = true;
      ProtectSystem = "strict";
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
}
