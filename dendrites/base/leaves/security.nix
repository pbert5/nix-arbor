{
  hostInventory,
  hostName,
  lib,
  pkgs,
  site,
  ...
}:
let
  bootstrapInventory = site.hostBootstrap or { };
  hostsInventory = site.hosts or { };
  hostBootstrap = bootstrapInventory.${hostName} or { };

  isLeader = lib.attrByPath [ "org" "clusterIdentity" "role" ] null hostInventory == "leader";
  isWorkstation = builtins.elem "system/workstation" (hostInventory.dendrites or [ ]);

  bootstrapTargetIPs = builtins.filter (
    target: target != null && builtins.match "^[0-9.]+$" target != null
  ) (lib.mapAttrsToList (_: bootstrap: bootstrap.targetHost or null) bootstrapInventory);
  leaderBootstrapIPs =
    builtins.filter (target: target != null && builtins.match "^[0-9.]+$" target != null)
      (
        lib.mapAttrsToList (leader: _: bootstrapInventory.${leader}.targetHost or null) (
          lib.filterAttrs (
            _: host: lib.attrByPath [ "org" "clusterIdentity" "role" ] null host == "leader"
          ) hostsInventory
        )
      );
  explicitTrustedIPs = lib.attrByPath [ "org" "security" "fail2ban" "trustedIPs" ] [ ] hostInventory;
in
{
  environment.systemPackages = with pkgs; [
    aide
    lsof
  ];

  services.fail2ban = {
    enable = true;
    ignoreIP = lib.unique (
      [
        "127.0.0.1/8"
        "::1"
      ]
      ++ bootstrapTargetIPs
      ++ leaderBootstrapIPs
      ++ lib.optionals (hostBootstrap ? targetHost) [ hostBootstrap.targetHost ]
      ++ explicitTrustedIPs
    );
  };

  services.opensnitch = {
    enable = lib.mkDefault (isLeader || isWorkstation);
    settings = {
      DefaultAction = "allow";
      DefaultDuration = "once";
      InterceptUnknown = false;
    };
  };
}
