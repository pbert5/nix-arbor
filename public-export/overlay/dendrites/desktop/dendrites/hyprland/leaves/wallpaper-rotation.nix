{
  lib,
  pkgs,
  ...
}:
let
  wallpaper = pkgs.writeShellApplication {
    name = "hypr-wallpaper";
    runtimeInputs = [
      pkgs.awww
      pkgs.procps
    ];
    text = ''
      case "''${1:-menu}" in
        menu)
          exec hypr-rofi-wallpaper
          ;;
        lock)
          pidof hyprlock >/dev/null || exec hyprlock
          ;;
        session-start)
          awww restore || awww clear 1e1e2eff
          ;;
        rotate)
          exit 0
          ;;
        *)
          printf 'usage: hypr-wallpaper [rotate|menu|session-start|lock]\n' >&2
          exit 2
          ;;
      esac
    '';
  };
in
{
  home.packages = [ wallpaper ];
  wayland.windowManager.hyprland.settings."$wallpaperMenu" =
    lib.mkForce "${lib.getExe wallpaper} menu";
}
