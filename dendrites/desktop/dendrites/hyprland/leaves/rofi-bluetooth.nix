{ lib, pkgs, ... }:
let
  rofi = lib.getExe pkgs.rofi;
  bluetoothctl = lib.getExe' pkgs.bluez "bluetoothctl";
  bluemanManager = lib.getExe' pkgs.blueman "blueman-manager";

  menu = pkgs.writeShellScriptBin "hypr-rofi-bluetooth" ''
    set -euo pipefail
    powered="$(${bluetoothctl} show | awk '/Powered:/ { print $2; exit }')"

    choose_device() {
      mode="$1"
      choice="$(
        ${bluetoothctl} devices \
          | while read -r _ addr name; do
              info="$(${bluetoothctl} info "$addr" 2>/dev/null || true)"
              [ -n "$info" ] || continue
              paired="$(printf '%s\n' "$info" | awk '/Paired:/ { print $2; exit }')"
              connected="$(printf '%s\n' "$info" | awk '/Connected:/ { print $2; exit }')"
              case "$mode" in
                paired) [ "$paired" = "yes" ] || continue ;;
                connected) [ "$connected" = "yes" ] || continue ;;
              esac
              status="paired"
              [ "$connected" = "yes" ] && status="connected"
              printf '%s (%s)\t%s\n' "''${name:-$addr}" "$status" "$addr"
            done \
          | ${rofi} -dmenu -i -p "Bluetooth devices"
      )"
      [ -n "$choice" ] || exit 0
      addr="$(printf '%s' "$choice" | cut -f2)"
      info="$(${bluetoothctl} info "$addr" 2>/dev/null || true)"
      connected="$(printf '%s\n' "$info" | awk '/Connected:/ { print $2; exit }')"
      paired="$(printf '%s\n' "$info" | awk '/Paired:/ { print $2; exit }')"
      if [ "$connected" = "yes" ]; then
        ${bluetoothctl} disconnect "$addr"
      elif [ "$paired" = "yes" ]; then
        ${bluetoothctl} connect "$addr"
      else
        ${bluetoothctl} pair "$addr"
      fi
    }

    choice="$(
      printf '%s\n' \
        "Turn Bluetooth ''$( [ "$powered" = "yes" ] && printf 'off' || printf 'on' )" \
        "Open Bluetooth Manager" \
        "Paired devices" \
        "Connected devices" \
      | ${rofi} -dmenu -i -p "Bluetooth"
    )"
    case "$choice" in
      "Turn Bluetooth on") ${bluetoothctl} power on ;;
      "Turn Bluetooth off") ${bluetoothctl} power off ;;
      "Open Bluetooth Manager") exec ${bluemanManager} ;;
      "Paired devices") choose_device paired ;;
      "Connected devices") choose_device connected ;;
    esac
  '';

  status = pkgs.writeShellScriptBin "hypr-waybar-bluetooth" ''
    powered="$(${bluetoothctl} show | awk '/Powered:/ { print $2; exit }' 2>/dev/null || true)"
    connected="$(${bluetoothctl} devices | while read -r _ addr _; do ${bluetoothctl} info "$addr" 2>/dev/null; done | awk '/Connected:/ && $2 == "yes" { c++ } END { print c + 0 }')"
    if [ "$powered" = "yes" ]; then
      if [ "$connected" -gt 0 ]; then printf 'bt %s\n' "$connected"; else printf 'bt on\n'; fi
    else
      printf 'bt off\n'
    fi
  '';
in
{
  home.packages = [
    menu
    status
  ];
}
