{ lib }:
let
  sanitizeName = lib.replaceStrings [ "/" " " ] [ "-" "-" ];

  walkFiles =
    root:
    let
      walk =
        prefix: dir:
        let
          entries = builtins.readDir dir;
        in
        lib.concatMap (
          name:
          let
            entryType = entries.${name};
            rel = if prefix == "" then name else "${prefix}/${name}";
            path = dir + "/${name}";
          in
          if entryType == "directory" then
            walk rel path
          else
            [
              {
                inherit path rel;
              }
            ]
        ) (builtins.attrNames entries);
    in
    walk "" root;

  entrySheets =
    registryKind: entry:
    let
      spec = entry.meta.cheatsheets or { };
      regexes = (spec.fileRegexes or [ ]) ++ lib.optionals (spec ? fileRegex) [ spec.fileRegex ];
      explicitFiles = spec.files or [ ];
      matchingFiles = lib.concatMap (
        regex:
        builtins.map (file: file.rel) (
          builtins.filter (file: builtins.match regex file.rel != null) (walkFiles entry.path)
        )
      ) regexes;
      files = lib.unique (explicitFiles ++ matchingFiles);
    in
    builtins.map (
      rel:
      let
        path = entry.path + "/${rel}";
      in
      if builtins.pathExists path then
        {
          inherit path registryKind;
          name = "${sanitizeName entry.key}-${builtins.baseNameOf rel}";
          owner = entry.key;
        }
      else
        throw "Dendritic cheatsheet '${rel}' declared by '${entry.key}' does not exist."
    ) files;

  collectFromRegistry =
    registryKind: registry:
    lib.concatLists (lib.mapAttrsToList (_: entry: entrySheets registryKind entry) registry);
in
{
  collect =
    { registries }:
    (collectFromRegistry "dendrite" registries.dendrites)
    ++ (collectFromRegistry "fruit" registries.fruits);
}
