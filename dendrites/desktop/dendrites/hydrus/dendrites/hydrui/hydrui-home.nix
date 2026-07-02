{ ... }:
{
  desktop.hyprland.extraMenuEntries.HydrUI = "xdg-open http://127.0.0.1:45870";

  xdg.desktopEntries.hydrui = {
    name = "HydrUI";
    genericName = "Hydrus Web UI";
    exec = "xdg-open http://127.0.0.1:45870";
    icon = "image-x-generic";
    terminal = false;
    categories = [
      "Graphics"
      "FileTools"
      "Utility"
    ];
  };
}
