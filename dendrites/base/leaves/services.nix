{
  hostInventory,
  lib,
  site,
  ...
}:
let
  leaderKeysDir = ../../../inventory/keys/leaders;
  leaderKeyFiles = builtins.map (name: leaderKeysDir + "/${name}") (
    builtins.attrNames (lib.filterAttrs (_: type: type == "regular") (builtins.readDir leaderKeysDir))
  );
  leaderAuthorizedKeysFromFiles = lib.concatMap (
    path: builtins.filter (line: line != "") (lib.splitString "\n" (builtins.readFile path))
  ) leaderKeyFiles;
  leaderUserAuthorizedKeys = lib.filter (key: key != null) (
    lib.mapAttrsToList (_hostName: record: lib.attrByPath [ "public" "sshPublicKey" ] null record) (
      lib.attrByPath [ "identities" "services" "leader-user-ssh" ] { } site
    )
  );
  rootSshBootstrap = lib.attrByPath [ "org" "bootstrap" "rootSsh" ] { } hostInventory;
  rootAuthorizedKeysFromFiles = lib.concatMap (
    path: builtins.filter (line: line != "") (lib.splitString "\n" (builtins.readFile path))
  ) (rootSshBootstrap.authorizedKeysFiles or [ ]);
  rootAuthorizedKeys = lib.unique (
    leaderAuthorizedKeysFromFiles
    ++ leaderUserAuthorizedKeys
    ++ (rootSshBootstrap.authorizedKeys or [ ])
    ++ rootAuthorizedKeysFromFiles
  );
in
{
  services.openssh.enable = true;
  services.openssh.settings = {
    PasswordAuthentication = false;
    KbdInteractiveAuthentication = false;
  };

  users.users.root.openssh.authorizedKeys.keys = lib.mkIf (
    rootAuthorizedKeys != [ ]
  ) rootAuthorizedKeys;
}
