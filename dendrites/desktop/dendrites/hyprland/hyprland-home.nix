{
  config,
  lib,
  pkgs,
  ...
}:
let
  extraMenuEntries = config.desktop.hyprland.extraMenuEntries;
  extraMenuLabels = lib.concatMapStringsSep " " lib.escapeShellArg (
    builtins.attrNames extraMenuEntries
  );
  extraMenuCases = lib.concatStringsSep "\n" (
    lib.mapAttrsToList (
      label: command: "${lib.escapeShellArg label}) exec ${command} ;;"
    ) extraMenuEntries
  );
  rofiCommand = "${lib.getExe pkgs.rofi}";
  dolphinCommand = "${lib.getExe pkgs.kdePackages.dolphin}";
  swayncClientCommand = "${lib.getExe' pkgs.swaynotificationcenter "swaync-client"}";
  uwsmCommand = "${lib.getExe pkgs.uwsm}";

  demoWallpaper =
    pkgs.runCommand "hyprland-demo-wallpaper.png" { nativeBuildInputs = [ pkgs.imagemagick ]; }
      ''
        magick -size 3440x1440 xc:'#1e1e2e' \
          -fill '#181825' -draw 'polygon 0,1120 3440,760 3440,1440 0,1440' \
          -fill '#313244' -draw 'polygon 0,980 3440,1180 3440,1440 0,1440' \
          -fill '#89b4fa' -draw 'rectangle 0,0 28,1440' \
          -fill '#a6e3a1' -draw 'rectangle 28,0 52,1440' \
          -fill '#f9e2af' -draw 'rectangle 52,0 76,1440' \
          -fill '#f38ba8' -draw 'rectangle 76,0 100,1440' \
          -fill '#45475a' -draw 'rectangle 260,300 3180,314' \
          -fill '#585b70' -draw 'rectangle 260,360 2540,374' \
          -fill '#cdd6f4' -draw 'rectangle 260,420 1480,434' \
          -fill '#89b4fa' -draw 'rectangle 260,480 980,494' \
        "$out"
      '';

  screenshot = pkgs.writeShellApplication {
    name = "hypr-screenshot";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.grim
      pkgs.slurp
      pkgs.wl-clipboard
    ];
    text = ''
      screenshot_dir="''${XDG_PICTURES_DIR:-$HOME/Pictures}/Screenshots"
      screenshot_path="$screenshot_dir/Screenshot-$(date +%Y-%m-%d-%H%M%S).png"
      mkdir -p "$screenshot_dir"

      case "''${1:-full}" in
        full)
          grim "$screenshot_path"
          ;;
        region)
          geometry="$(slurp)" || exit 0
          grim -g "$geometry" "$screenshot_path"
          ;;
        *)
          echo "usage: hypr-screenshot [full|region]" >&2
          exit 2
          ;;
      esac

      wl-copy --type image/png < "$screenshot_path"
    '';
  };

  shiftWorkspaceSet = pkgs.writeShellApplication {
    name = "hypr-shift-workspace-set";
    runtimeInputs = [ pkgs.jq ];
    text = ''
      direction="''${1:?usage: hypr-shift-workspace-set LEFT|RIGHT}"
      monitors="$(hyprctl -j monitors)"
      display_count="$(jq length <<< "$monitors")"
      focused_monitor="$(jq -r '.[] | select(.focused).name' <<< "$monitors")"

      case "$direction" in
        LEFT) offset="-$display_count" ;;
        RIGHT) offset="$display_count" ;;
        *) echo "usage: hypr-shift-workspace-set LEFT|RIGHT" >&2; exit 2 ;;
      esac

      jq -r --argjson offset "$offset" '
        .[] | [.name, (.activeWorkspace.id + $offset)] | @tsv
      ' <<< "$monitors" |
        while IFS=$'\t' read -r monitor workspace; do
          if (( workspace > 0 )); then
            hyprctl dispatch focusmonitor "$monitor"
            hyprctl dispatch workspace "$workspace"
          fi
        done

      hyprctl dispatch focusmonitor "$focused_monitor"
    '';
  };

  rofiKeybinds = pkgs.writeShellScriptBin "hypr-rofi-keybinds" ''
    cat <<'EOF' | ${rofiCommand} -dmenu -i -p "Keybinds" -theme-str 'listview { lines: 14; }' >/dev/null
    Super          Application launcher
    Super+Return   Open Kitty
    Super+K        Open Kitty
    Super+Space   Desktop menu
    Super+H       Hydrus library menu
    Super+W       Wi-Fi menu
    Super+Shift+W Wallpaper menu
    Super+B       Bluetooth menu
    Super+N       Notifications
    Super+F       Open Dolphin
    Super+Shift+F Toggle fullscreen
    Print           Capture all monitors
    Shift+Print     Capture a selected region
    Super+Escape  Power / logout menu
    Super+L       Lock session
    Super+P       Toggle pseudotile
    Super+Q       Close window
    Super+V       Toggle floating
    Super+Up      Toggle workspace overview on the current display
    Super+Shift+Up Toggle workspace overview on all displays
    Super+PageDown Next open workspace
    Super+PageUp   Previous open workspace
    Super+1..5     Switch workspace
    Super+MouseWheel Switch open workspaces
    Alt+Shift+1..0 Move window and follow to workspace 1..10
    Super+Shift+1..0 Move window silently to workspace 1..10
    Super+Shift+PageDown Move window to next open workspace
    Super+Shift+PageUp   Move window to previous open workspace
    Super+Shift+Left/Right Shift every display by one workspace set
    EOF
  '';

  rofiNotifications = pkgs.writeShellScriptBin "hypr-rofi-notifications" ''
    ${swayncClientCommand} -t -sw
  '';

  rofiNotificationsStatus = pkgs.writeShellScriptBin "hypr-waybar-notifications" ''
    count="$(${swayncClientCommand} -c -sw 2>/dev/null || printf '0')"
    dnd="$(${swayncClientCommand} -D -sw 2>/dev/null || printf 'false')"

    if [ "$dnd" = "true" ]; then
      printf 'dnd %s\n' "$count"
    elif [ "''${count:-0}" -gt 0 ] 2>/dev/null; then
      printf 'noti %s\n' "$count"
    else
      printf 'noti\n'
    fi
  '';

  rofiPower = pkgs.writeShellScriptBin "hypr-rofi-power" ''
    choice="$(
      printf '%s\n' \
        Lock \
        "Log out of Hyprland" \
        "Restart Waybar" \
        "Reload Hyprland config" \
        Suspend \
        Reboot \
        Shutdown \
      | ${rofiCommand} -dmenu -i -p "Power"
    )"

    case "$choice" in
      Lock) hypr-wallpaper lock ;;
      "Log out of Hyprland") ${uwsmCommand} stop ;;
      "Restart Waybar") systemctl --user restart waybar.service ;;
      "Reload Hyprland config") hyprctl reload ;;
      Suspend) systemctl suspend ;;
      Reboot) systemctl reboot ;;
      Shutdown) systemctl poweroff ;;
    esac
  '';

  rofiMenu = pkgs.writeShellScriptBin "hypr-rofi-menu" ''
    choice="$(printf '%s\n' Applications Windows Files ${extraMenuLabels} Wallpaper Wi-Fi Bluetooth Notifications Keybinds Power | ${rofiCommand} -dmenu -i -p "Menu")"

    case "$choice" in
      Applications) exec ${rofiCommand} -show drun ;;
      Windows) exec ${rofiCommand} -show window ;;
      Files) exec ${dolphinCommand} ;;
      ${extraMenuCases}
      Wallpaper) exec hypr-wallpaper menu ;;
      Wi-Fi) exec hypr-rofi-wifi ;;
      Bluetooth) exec hypr-rofi-bluetooth ;;
      Notifications) exec ${lib.getExe rofiNotifications} ;;
      Keybinds) exec ${lib.getExe rofiKeybinds} ;;
      Power) exec ${lib.getExe rofiPower} ;;
    esac
  '';

in
{
  imports = [
    ./leaves/menu-options.nix
    ./leaves/rofi-bluetooth.nix
    ./leaves/rofi-wallpaper.nix
    ./leaves/tailscale-wifi-menu.nix
  ];

  home.packages = [
    pkgs.hyprpolkitagent
    pkgs.kdePackages.dolphin
    pkgs.networkmanagerapplet
    pkgs.pwvucontrol
    rofiKeybinds
    rofiNotifications
    rofiNotificationsStatus
    rofiMenu
    rofiPower
    screenshot
  ];

  home.activation.bootstrapHyprlandWallpaper = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    wallpaper_dir="$HOME/Pictures/Wallpapers"
    wallpaper_path="$wallpaper_dir/hyprland-demo-wallpaper.png"

    ${pkgs.coreutils}/bin/install -d -m 0755 "$wallpaper_dir"
    if [ ! -e "$wallpaper_path" ]; then
      ${pkgs.coreutils}/bin/install -m 0644 ${demoWallpaper} "$wallpaper_path"
    fi
  '';

  xdg.configFile."uwsm/env".source =
    "${config.home.sessionVariablesPackage}/etc/profile.d/hm-session-vars.sh";
  xdg.configFile."hypr/hyprland.conf".force = true;

  xsession.preferStatusNotifierItems = true;

  services.gnome-keyring = {
    enable = true;
    components = [ "secrets" ];
  };

  wayland.windowManager.hyprland = {
    enable = true;
    package = null;
    portalPackage = null;
    configType = "hyprlang";
    systemd.enable = false;
    plugins = [ pkgs.hyprlandPlugins.hyprspace ];

    settings = {
      "$mod" = "SUPER";
      "$terminal" = "kitty";
      "$fileManager" = "dolphin";
      "$menu" = "rofi -show drun";
      "$desktopMenu" = "hypr-rofi-menu";
      "$powerMenu" = "hypr-rofi-power";
      "$wifiMenu" = "hypr-rofi-wifi";
      "$bluetoothMenu" = "hypr-rofi-bluetooth";
      "$wallpaperMenu" = "hypr-rofi-wallpaper";

      monitor = [
        "desc:LG Electronics LG ULTRAGEAR 411MXWE3J993,preferred,0x0,1"
        "desc:Acer Technologies ED340CU J0 55040A6463W01,preferred,2560x0,1"
        ",preferred,auto,1"
      ];

      workspace = [
        "1, monitor:desc:LG Electronics LG ULTRAGEAR 411MXWE3J993, default:true, persistent:true"
        "2, monitor:desc:Acer Technologies ED340CU J0 55040A6463W01, default:true, persistent:true"
      ];

      input = {
        kb_layout = "us";
        follow_mouse = 1;
        touchpad.natural_scroll = true;
        sensitivity = 0;
      };

      general = {
        gaps_in = 5;
        gaps_out = 10;
        border_size = 2;
        layout = "dwindle";
        "col.active_border" = "rgba(89b4faee) rgba(cba6f7ee) 45deg";
        "col.inactive_border" = "rgba(585b70aa)";
      };

      decoration = {
        rounding = 8;
        active_opacity = 1.0;
        inactive_opacity = 0.96;
        blur = {
          enabled = true;
          size = 6;
          passes = 2;
        };
      };

      animations.enabled = true;
      dwindle = {
        preserve_split = true;
      };
      misc = {
        disable_hyprland_logo = true;
        force_default_wallpaper = 0;
      };

      bindp =
        (map (keys: "${keys}, exec, ${pkgs.procps}/bin/pkill -x rofi || true") [
          "$mod, Return"
          "$mod, K"
          "$mod, SPACE"
          "$mod, H"
          "$mod, W"
          "$mod SHIFT, W"
          "$mod, B"
          "$mod, N"
          "$mod, F"
          "$mod SHIFT, F"
          ", Print"
          "SHIFT, Print"
          "$mod, Escape"
          "$mod, Q"
          "$mod SHIFT, E"
          "$mod, V"
          "$mod, L"
          "$mod, P"
          "$mod, left"
          "$mod, right"
          "$mod, up"
          "$mod SHIFT, up"
          "CTRL ALT, up"
          "$mod, down"
          "$mod, 1"
          "$mod, 2"
          "$mod, 3"
          "$mod, 4"
          "$mod, 5"
          "ALT SHIFT, 1"
          "ALT SHIFT, 2"
          "ALT SHIFT, 3"
          "ALT SHIFT, 4"
          "ALT SHIFT, 5"
          "ALT SHIFT, 6"
          "ALT SHIFT, 7"
          "ALT SHIFT, 8"
          "ALT SHIFT, 9"
          "ALT SHIFT, 0"
          "$mod SHIFT, 1"
          "$mod SHIFT, 2"
          "$mod SHIFT, 3"
          "$mod SHIFT, 4"
          "$mod SHIFT, 5"
          "$mod SHIFT, 6"
          "$mod SHIFT, 7"
          "$mod SHIFT, 8"
          "$mod SHIFT, 9"
          "$mod SHIFT, 0"
          "$mod, Page_Down"
          "$mod, Page_Up"
          "$mod SHIFT, Page_Down"
          "$mod SHIFT, Page_Up"
          "$mod SHIFT, left"
          "$mod SHIFT, right"
          "CTRL ALT, left"
          "CTRL ALT, right"
          "$mod, mouse_down"
          "$mod, mouse_up"
        ])
        ++ [
          "$mod, Return, exec, $terminal"
          "$mod, K, exec, $terminal"
          "$mod, SPACE, exec, $desktopMenu"
          "$mod, H, exec, hydrus-library-menu"
          "$mod, W, exec, $wifiMenu"
          "$mod SHIFT, W, exec, $wallpaperMenu"
          "$mod, B, exec, $bluetoothMenu"
          "$mod, N, exec, swaync-client -t -sw"
          "$mod, F, exec, $fileManager"
          "$mod SHIFT, F, fullscreen"
          ", Print, exec, ${lib.getExe screenshot} full"
          "SHIFT, Print, exec, ${lib.getExe screenshot} region"
          "$mod, Escape, exec, $powerMenu"
          "$mod, Q, killactive"
          "$mod SHIFT, E, exec, ${uwsmCommand} stop"
          "$mod, V, togglefloating"
          "$mod, L, exec, hypr-wallpaper lock"
          "$mod, P, pseudo"
          "$mod, left, movefocus, l"
          "$mod, right, movefocus, r"
          "$mod, up, exec, hyprctl dispatch overview:toggle"
          "$mod SHIFT, up, exec, hyprctl dispatch overview:toggle all"
          "CTRL ALT, up, exec, hyprctl dispatch overview:toggle all"
          "$mod, down, movefocus, d"
          "$mod, 1, workspace, 1"
          "$mod, 2, workspace, 2"
          "$mod, 3, workspace, 3"
          "$mod, 4, workspace, 4"
          "$mod, 5, workspace, 5"
          "ALT SHIFT, 1, movetoworkspace, 1"
          "ALT SHIFT, 2, movetoworkspace, 2"
          "ALT SHIFT, 3, movetoworkspace, 3"
          "ALT SHIFT, 4, movetoworkspace, 4"
          "ALT SHIFT, 5, movetoworkspace, 5"
          "ALT SHIFT, 6, movetoworkspace, 6"
          "ALT SHIFT, 7, movetoworkspace, 7"
          "ALT SHIFT, 8, movetoworkspace, 8"
          "ALT SHIFT, 9, movetoworkspace, 9"
          "ALT SHIFT, 0, movetoworkspace, 10"
          "$mod SHIFT, 1, movetoworkspacesilent, 1"
          "$mod SHIFT, 2, movetoworkspacesilent, 2"
          "$mod SHIFT, 3, movetoworkspacesilent, 3"
          "$mod SHIFT, 4, movetoworkspacesilent, 4"
          "$mod SHIFT, 5, movetoworkspacesilent, 5"
          "$mod SHIFT, 6, movetoworkspacesilent, 6"
          "$mod SHIFT, 7, movetoworkspacesilent, 7"
          "$mod SHIFT, 8, movetoworkspacesilent, 8"
          "$mod SHIFT, 9, movetoworkspacesilent, 9"
          "$mod SHIFT, 0, movetoworkspacesilent, 10"
          "$mod, Page_Down, workspace, e+1"
          "$mod, Page_Up, workspace, e-1"
          "$mod SHIFT, Page_Down, movetoworkspace, e+1"
          "$mod SHIFT, Page_Up, movetoworkspace, e-1"
          "$mod SHIFT, left, exec, ${lib.getExe shiftWorkspaceSet} LEFT"
          "$mod SHIFT, right, exec, ${lib.getExe shiftWorkspaceSet} RIGHT"
          "CTRL ALT, left, exec, ${lib.getExe shiftWorkspaceSet} LEFT"
          "CTRL ALT, right, exec, ${lib.getExe shiftWorkspaceSet} RIGHT"
          "$mod, mouse_down, workspace, e+1"
          "$mod, mouse_up, workspace, e-1"
        ];

      bindrp = [
        "$mod, Super_L, exec, ${pkgs.procps}/bin/pkill -x rofi || $menu"
      ];

      bindm = [
        "$mod, mouse:272, movewindow"
        "$mod, mouse:273, resizewindow"
      ];

      bindel = [
        ", XF86AudioRaiseVolume, exec, wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"
        ", XF86AudioLowerVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"
        ", XF86AudioMute, exec, wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"
        ", XF86AudioMicMute, exec, wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"
      ];
    };
  };

  programs.hyprlock = {
    enable = true;
    settings = {
      general = {
        hide_cursor = true;
        ignore_empty_input = true;
      };
      background = [
        {
          color = "rgb(1e1e2e)";
        }
      ];
      label = [
        {
          text = "$TIME12";
          font_size = 44;
          position = "0, 140";
          halign = "center";
          valign = "center";
          color = "rgb(cdd6f4)";
        }
        {
          text = "$USER";
          font_size = 22;
          position = "0, 32";
          halign = "center";
          valign = "center";
          color = "rgb(cdd6f4)";
        }
        {
          text = "Unlock with your password";
          font_size = 14;
          position = "0, -38";
          halign = "center";
          valign = "center";
          color = "rgb(9399b2)";
        }
      ];
      input-field = [
        {
          size = "300, 56";
          position = "0, -80";
          monitor = "";
          dots_center = true;
          fade_on_empty = false;
          font_color = "rgb(cdd6f4)";
          inner_color = "rgb(313244)";
          outer_color = "rgb(89b4fa)";
          outline_thickness = 3;
          placeholder_text = ''<span foreground="##cdd6f4">Password</span>'';
        }
      ];
    };
  };

  services.awww.enable = true;

  services.hypridle = {
    enable = true;
    settings = {
      general = {
        lock_cmd = "hypr-wallpaper lock";
        before_sleep_cmd = "loginctl lock-session";
        after_sleep_cmd = "hyprctl dispatch dpms on";
      };
      listener = [
        {
          timeout = 600;
          on-timeout = "loginctl lock-session";
        }
        {
          timeout = 660;
          on-timeout = "hyprctl dispatch dpms off";
          on-resume = "hyprctl dispatch dpms on";
        }
      ];
    };
  };

  programs.kitty = {
    enable = true;
    settings = {
      confirm_os_window_close = 0;
      enable_audio_bell = false;
      remember_window_size = false;
      initial_window_width = 1200;
      initial_window_height = 760;
    };
  };

  programs.rofi = {
    enable = true;
    package = pkgs.rofi;
    terminal = "kitty";
    extraConfig = {
      click-to-exit = true;
      modi = "drun,run,window";
      show-icons = true;
      drun-display-format = "{icon} {name}";
      display-drun = "Applications";
      display-run = "Command";
      display-window = "Windows";
    };
  };

  programs.waybar = {
    enable = true;
    systemd.enable = true;
    settings.mainBar = {
      layer = "top";
      position = "top";
      height = 34;
      spacing = 8;
      modules-left = [
        "custom/launcher"
        "hyprland/workspaces"
        "custom/keybinds"
      ];
      modules-center = [ "hyprland/window" ];
      modules-right = [
        "custom/notifications"
        "custom/bluetooth"
        "custom/tailscale"
        "network"
        "tray"
        "pulseaudio"
        "cpu"
        "memory"
        "clock"
        "custom/power"
      ];
      "custom/launcher" = {
        format = " apps ";
        tooltip = false;
        on-click = "hypr-rofi-menu";
      };
      "hyprland/workspaces" = {
        disable-scroll = true;
        all-outputs = true;
      };
      "custom/keybinds" = {
        format = " keys ";
        tooltip = false;
        on-click = "hypr-rofi-keybinds";
      };
      "custom/notifications" = {
        exec = "hypr-waybar-notifications";
        interval = 5;
        on-click = "swaync-client -t -sw";
        on-click-right = "swaync-client -d -sw";
      };
      "custom/bluetooth" = {
        exec = "hypr-waybar-bluetooth";
        interval = 5;
        on-click = "hypr-rofi-bluetooth";
        on-click-right = "blueman-manager";
      };
      "custom/tailscale" = {
        exec = "hypr-waybar-tailscale";
        interval = 5;
        on-click = "hypr-rofi-wifi";
        tooltip = false;
      };
      network = {
        format-wifi = "wifi {essid} {signalStrength}%";
        format-ethernet = "net {ipaddr}/{cidr}";
        format-disconnected = "offline";
        tooltip-format = "{ifname}: {ipaddr}/{cidr}";
        on-click = "hypr-rofi-wifi";
        on-click-right = "nm-connection-editor";
      };
      tray = {
        spacing = 8;
      };
      pulseaudio = {
        format = "vol {volume}%";
        format-muted = "muted";
        on-click = "pwvucontrol";
      };
      cpu.format = "cpu {usage}%";
      memory.format = "mem {}%";
      clock = {
        format = "{:%a %b %d  %I:%M %p}";
        tooltip-format = "<tt><small>{calendar}</small></tt>";
      };
      "custom/power" = {
        format = " power ";
        tooltip = false;
        on-click = "hypr-rofi-power";
      };
    };
    style = ''
      * {
        border: none;
        border-radius: 0;
        font-family: sans-serif;
        font-size: 13px;
        min-height: 0;
      }

      window#waybar {
        background: rgba(24, 24, 37, 0.94);
        color: #cdd6f4;
      }

      #custom-launcher,
      #custom-keybinds,
      #custom-notifications,
      #custom-bluetooth,
      #custom-tailscale,
      #custom-power,
      #network,
      #pulseaudio,
      #cpu,
      #memory,
      #clock {
        padding: 0 10px;
      }

      #custom-launcher,
      #custom-keybinds,
      #custom-notifications,
      #custom-bluetooth,
      #custom-power {
        background: rgba(49, 50, 68, 0.95);
        color: #89b4fa;
      }

      #workspaces button {
        padding: 0 8px;
        color: #bac2de;
      }

      #workspaces button.active {
        background: #89b4fa;
        color: #1e1e2e;
      }
    '';
  };

  services.swaync = {
    enable = true;
    settings = {
      positionX = "right";
      positionY = "top";
      layer = "overlay";
      "control-center-layer" = "top";
      "layer-shell" = true;
      "layer-shell-cover-screen" = true;
      timeout = 8;
      "timeout-low" = 4;
      "timeout-critical" = 0;
      "notification-window-width" = 420;
      "control-center-width" = 420;
      "fit-to-screen" = true;
      "notification-grouping" = true;
      "hide-on-action" = true;
      "hide-on-clear" = false;
      "text-empty" = "No notifications";
    };
  };

  services.network-manager-applet.enable = true;
  services.blueman-applet.enable = true;

  xdg.mimeApps = {
    enable = true;
    defaultApplications."inode/directory" = [ "org.kde.dolphin.desktop" ];
    defaultApplications."image/jpeg" = [ "imv.desktop" ];
    defaultApplications."image/png" = [ "imv.desktop" ];
    defaultApplications."image/gif" = [ "imv.desktop" ];
    defaultApplications."image/webp" = [ "imv.desktop" ];
    defaultApplications."image/bmp" = [ "imv.desktop" ];
    defaultApplications."image/tiff" = [ "imv.desktop" ];
    defaultApplications."image/svg+xml" = [ "imv.desktop" ];
    defaultApplications."image/x-portable-anymap" = [ "imv.desktop" ];
  };
  xdg.dataFile."applications/mimeapps.list".force = true;

  systemd.user.services = {
    awww-restore = {
      Unit = {
        Description = "Restore wallpaper after awww starts";
        After = [
          "awww.service"
          config.wayland.systemd.target
        ];
        PartOf = [ config.wayland.systemd.target ];
        ConditionEnvironment = "WAYLAND_DISPLAY";
      };
      Service = {
        Type = "oneshot";
        ExecStart = "${config.home.profileDirectory}/bin/hypr-wallpaper session-start";
      };
      Install.WantedBy = [ config.wayland.systemd.target ];
    };

    hyprpolkitagent = {
      Unit = {
        Description = "Hyprland Polkit authentication agent";
        After = [ config.wayland.systemd.target ];
        PartOf = [ config.wayland.systemd.target ];
        ConditionEnvironment = "WAYLAND_DISPLAY";
      };
      Service = {
        ExecStart = "${pkgs.hyprpolkitagent}/libexec/hyprpolkitagent";
        Restart = "on-failure";
      };
      Install.WantedBy = [ config.wayland.systemd.target ];
    };
  };
}
