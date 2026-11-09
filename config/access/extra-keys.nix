{ config, lib, ... }:
let
  grants = builtins.fromJSON (builtins.readFile ./extra-keys.json);
  hostGrants = grants.${config.networking.hostName} or { };
in
{
  users.users = lib.mapAttrs (_: keys: { openssh.authorizedKeys.keys = keys; }) hostGrants;
}
