{ lib }:
{
  exportedHosts = inventory:
    lib.filterAttrs (_: host: host.exported or true) inventory.hosts;

  firstOrNull = list:
    if list == [ ] then
      null
    else
      builtins.head list;

  formatNames = names: lib.concatStringsSep ", " names;

  legacyRoleFromDendrite = name:
    if name == "workstation" then
      "workstation"
    else if name == "compute-worker" then
      "compute-worker"
    else
      null;

  missingFrom = available: requested:
    builtins.filter (name: !(builtins.elem name available)) requested;

  normalizeLegacyDendriteName = name:
    if name == "host-common" then
      "base"
    else if name == "game-library" then
      "media/game-library"
    else if name == "desktop-gnome" then
      "desktop/gnome"
    else if name == "desktop-cinnamon" then
      "desktop/cinnamon"
    else if name == "tape-library" then
      "storage/tape"
    else if builtins.elem name [
      "workstation"
      "compute-worker"
      "home-manager"
    ] then
      null
    else
      name;

  normalizeOverrideName = name:
    if lib.hasPrefix "host-" name then
      lib.removePrefix "host-" name
    else
      name;

  removeNulls = list: builtins.filter (value: value != null) list;
}
