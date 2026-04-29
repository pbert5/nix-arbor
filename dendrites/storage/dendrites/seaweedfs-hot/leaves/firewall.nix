{
  config,
  lib,
  site,
  hostInventory,
  hostName,
  ...
}:
let
  fabric = site.storageFabric or { };
  hotPool = lib.attrByPath [ "seaweedfs" "hotPool" ] { } fabric;
  masterPort = hotPool.masterPort or 9333;
  volumePort = hotPool.volumePort or 8080;
  filerPort = hotPool.filerPort or 8888;
  s3Port = hotPool.s3Port or 8333;
  masterGrpcPort = masterPort + 10000;
  volumeGrpcPort = volumePort + 10000;
  filerGrpcPort = filerPort + 10000;
  s3Enable = lib.attrByPath [ "s3" "enable" ] false hotPool;
  # Only the Yggdrasil interface is allowed to carry SeaweedFS traffic.
  yggIfName = lib.attrByPath [
    "networks"
    "privateYggdrasil"
    "defaults"
    "ifName"
  ] "ygg0" site;
  isMaster = builtins.elem "seaweed-master" (hostInventory.roles or [ ]);
  isVolume = builtins.elem "seaweed-volume" (hostInventory.roles or [ ]);
  isFiler = builtins.elem "seaweed-filer" (hostInventory.roles or [ ]);
  isS3 = builtins.elem "seaweed-s3" (hostInventory.roles or [ ]);
  openPorts =
    lib.optionals isMaster [
      masterPort
      masterGrpcPort
    ]
    ++ lib.optionals isVolume [
      volumePort
      volumeGrpcPort
    ]
    ++ lib.optionals isFiler [
      filerPort
      filerGrpcPort
    ]
    ++ lib.optionals (isS3 && s3Enable) [ s3Port ];
  globalExposedPorts = builtins.filter (
    port: builtins.elem port (config.networking.firewall.allowedTCPPorts or [ ])
  ) openPorts;
  exposedInterfaces = lib.filterAttrs (
    ifName: iface:
    ifName != yggIfName && lib.any (port: builtins.elem port (iface.allowedTCPPorts or [ ])) openPorts
  ) (config.networking.firewall.interfaces or { });
in
lib.mkIf (openPorts != [ ]) {
  networking.firewall.interfaces.${yggIfName}.allowedTCPPorts = openPorts;

  # Explicit assertion: SeaweedFS must not be reachable on public interfaces.
  assertions = [
    {
      assertion = globalExposedPorts == [ ] && exposedInterfaces == { };
      message = ''
        SeaweedFS ports (${lib.concatMapStringsSep ", " toString openPorts}) must not
        appear in networking.firewall.allowedTCPPorts or on non-${yggIfName}
        interfaces.  They are restricted to the ${yggIfName} interface only.
        Globally exposed ports: ${lib.concatMapStringsSep ", " toString globalExposedPorts}
        Exposed interfaces: ${lib.concatStringsSep ", " (builtins.attrNames exposedInterfaces)}
      '';
    }
  ];
}
