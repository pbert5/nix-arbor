{
  hostName,
  lib,
  site,
  ...
}:
let
  keysByUser = lib.attrByPath [ "guestAccess" "ssh" "byHostUser" hostName ] { } site;
in
{
  users.users = lib.mapAttrs (_userName: keys: {
    openssh.authorizedKeys.keys = lib.mkAfter keys;
  }) keysByUser;
}
