{
  hostInventory,
  hostName,
  lib,
  site,
  ...
}:
let
  organizrOrg = lib.attrByPath [ "org" "organizr" ] { } hostInventory;
  adminUserName = organizrOrg.setup.admin.user or "ash";
  adminUser = site.users.${adminUserName} or { };
  adminHome = adminUser.home or { };
  adminNixos = adminUser.nixos or { };
  adminOrg = adminUser.org or { };
  endpoint = site.ports.organizr;
in
{
  imports = [ ./nix/organizr-module.nix ];

  services.organizr = {
    enable = true;
    inherit endpoint;
    openFirewall = organizrOrg.openFirewall or true;
    stateDir = organizrOrg.stateDir or "/var/lib/organizr";
    puid = organizrOrg.puid or 911;
    pgid = organizrOrg.pgid or 911;
    setup = lib.recursiveUpdate
      {
        enable = true;
        installType = "personal";
        admin = {
          username = adminHome.username or adminUserName;
          email = adminOrg.email or "${adminUserName}@${hostName}.local";
          passwordSeed = adminNixos.hashedPassword or null;
        };
      }
      (organizrOrg.setup or { });
  };
}
