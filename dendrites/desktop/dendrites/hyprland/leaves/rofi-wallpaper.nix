{ lib, pkgs, ... }:
let
  awww = lib.getExe pkgs.awww;
  rofi = lib.getExe pkgs.rofi;
  menu = pkgs.writeShellScriptBin "hypr-rofi-wallpaper" ''
    set -euo pipefail
    restore_or_clear() {
      if ${awww} restore >/dev/null 2>&1 \
        && ! ${awww} query | grep -qi 'color: 000000'; then
        return 0
      fi
      ${awww} clear 1e1e2eff
    }
    wallpaper_dirs=()
    for dir in "$HOME/Pictures/Wallpapers" "$HOME/Pictures"; do
      [ -d "$dir" ] && wallpaper_dirs+=("$dir")
    done
    entries="$(
      printf 'Restore previous\t__restore__\n'
      printf 'Clear wallpaper\t__clear__\n'
      if [ "''${#wallpaper_dirs[@]}" -gt 0 ]; then
        find "''${wallpaper_dirs[@]}" -maxdepth 2 -type f \
          \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' -o -iname '*.gif' \) \
          2>/dev/null | awk '!seen[$0]++' \
          | while read -r path; do printf '%s\t%s\n' "$(basename "$path")" "$path"; done
      fi
    )"
    choice="$(printf '%s\n' "$entries" | ${rofi} -dmenu -i -p "Wallpaper")"
    [ -n "$choice" ] || exit 0
    path="$(printf '%s' "$choice" | cut -f2-)"
    case "$path" in
      __restore__) restore_or_clear ;;
      __clear__) ${awww} clear 1e1e2eff ;;
      *)
        exec ${awww} img "$path" \
          --transition-type any \
          --transition-duration 1.2 \
          --transition-step 90
        ;;
    esac
  '';
in
{
  home.packages = [ menu ];
}
