{ lib }:
let
  directoryNames = root:
    builtins.attrNames (lib.filterAttrs (_: type: type == "directory") (builtins.readDir root));

  requirePath = path: message:
    if builtins.pathExists path then
      path
    else
      throw message;

  mkPassiveEntry = { key, dir, fileName, metaRequired ? false }:
    let
      entryPath = requirePath (dir + "/${fileName}") "Missing registry entrypoint '${toString (dir + "/${fileName}")}'.";
      metaPath = dir + "/meta.nix";
    in
    {
      inherit key;
      module = import entryPath;
      path = dir;
    }
    // lib.optionalAttrs metaRequired {
      meta = import (requirePath metaPath "Missing metadata '${toString metaPath}'.");
    };
in
{
  mkDendriteRegistry = root:
    let
      collectEntries =
        prefix: currentRoot:
        let
          names = directoryNames currentRoot;
        in
        lib.concatMap
          (name:
            let
              dir = currentRoot + "/${name}";
              entryPath = dir + "/${name}.nix";
              metaPath = dir + "/meta.nix";
              isEntry = builtins.pathExists entryPath && builtins.pathExists metaPath;
              nextPrefix = if isEntry then (if prefix == "" then name else "${prefix}/${name}") else prefix;
            in
            lib.optionals isEntry [
              {
                name = nextPrefix;
                value = mkPassiveEntry {
                  key = nextPrefix;
                  inherit dir;
                  fileName = "${name}.nix";
                  metaRequired = true;
                };
              }
            ]
            ++ lib.optionals (isEntry || name == "dendrites") (collectEntries nextPrefix dir))
          names;
    in
    builtins.listToAttrs (collectEntries "" root);

  mkFruitRegistry = root:
    builtins.listToAttrs (
      builtins.map
        (name: {
          name = name;
          value = mkPassiveEntry {
            key = name;
            dir = root + "/${name}";
            fileName = "${name}.nix";
            metaRequired = true;
          };
        })
        (directoryNames root)
    );

  mkHomeRegistry = root:
    let
      sharedRoot = root + "/shared";
      sharedEntries =
        if builtins.pathExists sharedRoot then
          builtins.map
            (name: {
              name = "shared/${name}";
              value = mkPassiveEntry {
                key = "shared/${name}";
                dir = sharedRoot + "/${name}";
                fileName = "${name}.nix";
              };
            })
            (directoryNames sharedRoot)
        else
          [ ];

      userEntries =
        builtins.map
          (name: {
            name = name;
            value = mkPassiveEntry {
              key = name;
              dir = root + "/${name}";
              fileName = "${name}.nix";
            };
          })
          (builtins.filter (name: name != "shared") (directoryNames root));
    in
    builtins.listToAttrs (sharedEntries ++ userEntries);

  mkHostRegistry = root:
    builtins.listToAttrs (
      builtins.map
        (name: {
          name = name;
          value = mkPassiveEntry {
            key = name;
            dir = root + "/${name}";
            fileName = "${name}.nix";
          };
        })
        (directoryNames root)
    );
}
