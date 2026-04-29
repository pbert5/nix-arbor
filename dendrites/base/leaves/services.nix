{
  hostInventory,
  lib,
  ...
}:
let
  leaderKeysDir = ../../../inventory/keys/leaders;
  leaderKeyFiles =
    builtins.map
      (name: leaderKeysDir + "/${name}")
      (
        builtins.attrNames
          (
            lib.filterAttrs
              (_: type: type == "regular")
              (builtins.readDir leaderKeysDir)
          )
      );
  leaderAuthorizedKeysFromFiles =
    lib.concatMap
      (path:
        builtins.filter
          (line: line != "")
          (lib.splitString "\n" (builtins.readFile path)))
      leaderKeyFiles;
  rootSshBootstrap = lib.attrByPath [ "org" "bootstrap" "rootSsh" ] { } hostInventory;
  rootAuthorizedKeysFromFiles =
    lib.concatMap
      (path:
        builtins.filter
          (line: line != "")
          (lib.splitString "\n" (builtins.readFile path)))
      (rootSshBootstrap.authorizedKeysFiles or [ ]);
  rootAuthorizedKeys = lib.unique (
    leaderAuthorizedKeysFromFiles
    ++ (rootSshBootstrap.authorizedKeys or [ ])
    ++ rootAuthorizedKeysFromFiles
  );
in
{
  services.openssh.enable = true;

  users.users.root.openssh.authorizedKeys.keys = lib.mkIf (rootAuthorizedKeys != [ ]) rootAuthorizedKeys;
}
