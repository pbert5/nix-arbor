{ lib, ... }:
{
  options.desktop.hyprland.extraMenuEntries = lib.mkOption {
    type = lib.types.attrsOf lib.types.str;
    default = { };
    description = "Additional commands exposed by selectable desktop dendrites.";
  };
}
