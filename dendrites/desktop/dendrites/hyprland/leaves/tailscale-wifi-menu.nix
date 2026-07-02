{ lib, pkgs, ... }:
let
  rofiCommand = "${lib.getExe pkgs.rofi}";
  nmcliCommand = "${lib.getExe' pkgs.networkmanager "nmcli"}";
  nmConnectionEditorCommand = "${lib.getExe' pkgs.networkmanagerapplet "nm-connection-editor"}";
  tailscaleCommand = "${lib.getExe pkgs.tailscale}";

  rofiWifi = pkgs.writeShellScriptBin "hypr-rofi-wifi" ''
    set -euo pipefail

    wifi_dev="$(${nmcliCommand} -t -f DEVICE,TYPE,STATE device status | awk -F: '$2 == "wifi" { print $1; exit }')"
    wifi_state="$(${nmcliCommand} radio wifi)"

    current_wifi() {
      ${nmcliCommand} -g NAME,DEVICE,TYPE connection show --active \
        | paste - - - \
        | awk -F '\t' '$3 == "802-11-wireless" { print $1 " on " $2; found = 1; exit } END { if (!found) print "No active Wi-Fi connection"; }'
    }

    nearby_networks() {
      ${nmcliCommand} --wait 10 device wifi list --rescan yes >/dev/null 2>&1 || true

      choice="$(
        ${nmcliCommand} -g IN-USE,BSSID,SSID,SIGNAL,SECURITY device wifi list \
          | paste - - - - - \
          | awk -F '\t' '
              {
                inuse = ($1 == "*") ? "[*]" : "[ ]";
                bssid = $2;
                ssid = $3 == "" ? "<hidden>" : $3;
                signal = $4 == "" ? "?" : $4;
                security = $5 == "" ? "open" : $5;
                printf("%s %s  %s%%  %s\t%s\t%s\t%s\n", inuse, ssid, signal, security, bssid, ssid, security);
              }
            ' \
          | ${rofiCommand} -dmenu -i -p "Nearby Wi-Fi"
      )"

      [ -n "$choice" ] || exit 0

      bssid="$(printf '%s' "$choice" | cut -f2)"
      ssid="$(printf '%s' "$choice" | cut -f3)"
      security="$(printf '%s' "$choice" | cut -f4)"

      if [ "$ssid" = "<hidden>" ]; then
        ssid=""
      fi

      if [ -n "$security" ] && [ "$security" != "open" ] && [ "$security" != "--" ]; then
        prompt_target="''${ssid:-$bssid}"
        password="$(printf "" | ${rofiCommand} -dmenu -password -p "Password for $prompt_target")"
        [ -n "$password" ] || exit 0
        if [ -n "$ssid" ]; then
          ${nmcliCommand} device wifi connect "$bssid" name "$ssid" ifname "$wifi_dev" password "$password"
        else
          ${nmcliCommand} device wifi connect "$bssid" ifname "$wifi_dev" password "$password"
        fi
      else
        if [ -n "$ssid" ]; then
          ${nmcliCommand} device wifi connect "$bssid" name "$ssid" ifname "$wifi_dev"
        else
          ${nmcliCommand} device wifi connect "$bssid" ifname "$wifi_dev"
        fi
      fi
    }

    saved_networks() {
      choice="$(
        ${nmcliCommand} -g NAME,TYPE connection show \
          | paste - - \
          | awk -F '\t' '$2 == "802-11-wireless" { print $1 }' \
          | ${rofiCommand} -dmenu -i -p "Saved Wi-Fi"
      )"

      [ -n "$choice" ] || exit 0
      ${nmcliCommand} connection up id "$choice"
    }

    tailscale_status() {
      ${tailscaleCommand} status --json 2>/dev/null \
        | ${lib.getExe pkgs.jq} -r '
            "Backend: \(.BackendState)",
            "Tailscale IPs: \(.Self.TailscaleIPs | join(", "))",
            "Exit node: \(if .Self.ExitNode then .Self.HostName else "none selected" end)"
          ' \
        | ${rofiCommand} -dmenu -i -p "Tailscale status" >/dev/null
    }

    select_exit_node() {
      filter="''${1:-}"
      prompt="''${2:-Exit node}"

      entries="$(
        ${tailscaleCommand} status --json 2>/dev/null \
          | ${lib.getExe pkgs.jq} -r --arg filter "$filter" '
              ([ .Self ] + (.Peer | to_entries | map(.value)))
              | .[]
              | select(.ExitNodeOption == true or .ExitNode == true)
              | select($filter == "" or (((.HostName // "") + " " + (.DNSName // "")) | test($filter; "i")))
              | [
                  (if .ExitNode then "[current]" else "[ ]" end),
                  (.HostName // "unknown"),
                  (.DNSName // ""),
                  (.TailscaleIPs[0] // "")
                ]
              | @tsv
            '
      )"

      if [ -z "$entries" ]; then
        printf 'No matching Tailscale exit nodes are currently visible.\n' \
          | ${rofiCommand} -dmenu -i -p "$prompt" >/dev/null
        return 0
      fi

      choice="$(printf '%s\n' "$entries" | ${rofiCommand} -dmenu -i -p "$prompt")"
      [ -n "$choice" ] || return 0

      node="$(printf '%s' "$choice" | cut -f4)"
      [ -n "$node" ] || return 0

      if ${tailscaleCommand} set --exit-node="$node" --exit-node-allow-lan-access=false --accept-dns=true >/tmp/hypr-rofi-tailscale.log 2>&1; then
        printf 'Using Tailscale exit node: %s\nLAN access disabled; Tailscale DNS accepted.\n' "$node" \
          | ${rofiCommand} -dmenu -i -p "Tailscale" >/dev/null
      else
        ${rofiCommand} -dmenu -i -p "Tailscale error" </tmp/hypr-rofi-tailscale.log >/dev/null
      fi
    }

    tailscale_menu() {
      choice="$(
        printf '%s\n' \
          "Select exit node" \
          "Select Mullvad exit node" \
          "Use suggested exit node" \
          "Clear exit node" \
          "Show status" \
        | ${rofiCommand} -dmenu -i -p "Tailscale"
      )"

      case "$choice" in
        "Select exit node") select_exit_node "" "Exit node" ;;
        "Select Mullvad exit node") select_exit_node "mullvad" "Mullvad exit node" ;;
        "Use suggested exit node")
          suggestion_output="$(${tailscaleCommand} exit-node suggest 2>&1 || true)"
          suggestion="$(printf '%s\n' "$suggestion_output" | awk '/^Use / { print $NF; exit }')"
          if [ -z "$suggestion" ]; then
            printf '%s\n' "$suggestion_output" | ${rofiCommand} -dmenu -i -p "Tailscale" >/dev/null
            return 0
          fi

          if [ -n "$suggestion" ] && ${tailscaleCommand} set --exit-node="$suggestion" --exit-node-allow-lan-access=false --accept-dns=true >/tmp/hypr-rofi-tailscale.log 2>&1; then
            printf 'Using suggested exit node: %s\nLAN access disabled; Tailscale DNS accepted.\n' "$suggestion" \
              | ${rofiCommand} -dmenu -i -p "Tailscale" >/dev/null
          else
            ${rofiCommand} -dmenu -i -p "Tailscale error" </tmp/hypr-rofi-tailscale.log >/dev/null
          fi
          ;;
        "Clear exit node")
          if ${tailscaleCommand} set --exit-node= --exit-node-allow-lan-access=false >/tmp/hypr-rofi-tailscale.log 2>&1; then
            printf 'Tailscale exit node cleared.\n' | ${rofiCommand} -dmenu -i -p "Tailscale" >/dev/null
          else
            ${rofiCommand} -dmenu -i -p "Tailscale error" </tmp/hypr-rofi-tailscale.log >/dev/null
          fi
          ;;
        "Show status") tailscale_status ;;
      esac
    }

    choice="$(
      printf '%s\n' \
        "Turn Wi-Fi ''$( [ "$wifi_state" = "enabled" ] && printf 'off' || printf 'on' )" \
        "Show nearby networks" \
        "Connect to saved networks" \
        "Tailscale exit nodes" \
        "Disconnect" \
        "Show current connection" \
        "Open advanced settings" \
      | ${rofiCommand} -dmenu -i -p "Wi-Fi"
    )"

    case "$choice" in
      "Turn Wi-Fi on") ${nmcliCommand} radio wifi on ;;
      "Turn Wi-Fi off") ${nmcliCommand} radio wifi off ;;
      "Show nearby networks") nearby_networks ;;
      "Connect to saved networks") saved_networks ;;
      "Tailscale exit nodes") tailscale_menu ;;
      "Disconnect") [ -n "$wifi_dev" ] && ${nmcliCommand} device disconnect "$wifi_dev" ;;
      "Show current connection") current_wifi | ${rofiCommand} -dmenu -i -p "Current Wi-Fi" >/dev/null ;;
      "Open advanced settings") exec ${nmConnectionEditorCommand} ;;
    esac
  '';

  tailscaleExitNodeStatus = pkgs.writeShellScriptBin "hypr-waybar-tailscale" ''
    ${tailscaleCommand} status --json 2>/dev/null \
      | ${lib.getExe pkgs.jq} -r '
          .ExitNodeStatus.ID as $id
          | if $id == null then
              empty
            else
              ([.Self] + (.Peer | to_entries | map(.value)))
              | map(select(.ID == $id))
              | .[0]
              | "vpn \(.HostName // .DNSName // "exit node")"
            end
        '
  '';
in
{
  home.packages = [
    rofiWifi
    tailscaleExitNodeStatus
  ];
}
