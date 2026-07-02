{
  lib,
  pkgs,
  site,
  ...
}:
let
  endpoints = import ../../../../../../lib/endpoints.nix { inherit lib; };
  hydruiServer = pkgs.callPackage ./_packages/hydrui-server.nix { };
  endpoint = endpoints.normalizeEndpoint 45870 (site.ports.hydrui or { });
  firewallInterface = endpoint.firewallInterface or "tailscale0";
in
{
  home-manager.sharedModules = [
    ./hydrui-home.nix
  ];

  environment.systemPackages = [
    hydruiServer
  ];

  systemd.services.hydrui-server = {
    description = "HydrUI web interface";
    documentation = [ "https://hydrui.dev" ];
    wantedBy = [ "multi-user.target" ];
    wants = [ "network-online.target" ];
    after = [ "network-online.target" ];

    serviceConfig = {
      DynamicUser = true;
      ExecStart = ''
        ${lib.getExe hydruiServer} \
          -nogui=true \
          -listen=${endpoint.bind}:${toString endpoint.port} \
          -server-mode=false \
          -acme=false
      '';
      LockPersonality = true;
      MemoryDenyWriteExecute = true;
      NoNewPrivileges = true;
      PrivateDevices = true;
      PrivateMounts = true;
      PrivateTmp = true;
      ProtectClock = true;
      ProtectControlGroups = true;
      ProtectHome = true;
      ProtectHostname = true;
      ProtectKernelLogs = true;
      ProtectKernelModules = true;
      ProtectKernelTunables = true;
      ProtectSystem = "strict";
      Restart = "on-failure";
      RestartSec = 10;
      RestrictNamespaces = true;
      RestrictRealtime = true;
      StateDirectory = "hydrui-server";
      StateDirectoryMode = "0700";
      SystemCallArchitectures = "native";
      SystemCallFilter = [
        "@system-service"
        "~@privileged"
      ];
      UMask = "077";
    };

    unitConfig.StartLimitBurst = 5;
  };

  networking.firewall.interfaces.${firewallInterface}.allowedTCPPorts = [
    endpoint.port
  ];
}
