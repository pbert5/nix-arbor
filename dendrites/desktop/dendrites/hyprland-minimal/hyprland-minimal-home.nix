{ lib, pkgs, ... }:
let
  terminalCommand = lib.getExe pkgs.kitty;
  launcherCommand = "${lib.getExe pkgs.rofi} -show drun";
in
{
  home.packages = [
    pkgs.hyprpolkitagent
    pkgs.kitty
    pkgs.rofi
  ];

  xdg.configFile."hypr/hyprland.conf".force = true;

  wayland.windowManager.hyprland = {
    enable = true;
    package = null;
    portalPackage = null;
    configType = "hyprlang";
    systemd.enable = false;

    settings = {
      "$mod" = "SUPER";
      "$terminal" = terminalCommand;
      "$menu" = launcherCommand;

      monitor = [ ",preferred,auto,1" ];

      exec-once = [
        (lib.getExe pkgs.hyprpolkitagent)
      ];

      input = {
        kb_layout = "us";
        follow_mouse = 1;
        touchpad.natural_scroll = true;
      };

      general = {
        gaps_in = 4;
        gaps_out = 8;
        border_size = 2;
        layout = "dwindle";
      };

      decoration = {
        rounding = 4;
        blur.enabled = false;
      };

      animations.enabled = false;

      misc = {
        disable_hyprland_logo = false;
        force_default_wallpaper = 1;
      };

      bind = [
        "$mod, Return, exec, $terminal"
        "$mod, D, exec, $menu"
        "$mod, Q, killactive"
        "$mod SHIFT, E, exit"
        "$mod, V, togglefloating"
        "$mod, F, fullscreen"
        "$mod, left, movefocus, l"
        "$mod, right, movefocus, r"
        "$mod, up, movefocus, u"
        "$mod, down, movefocus, d"
        "$mod, 1, workspace, 1"
        "$mod, 2, workspace, 2"
        "$mod, 3, workspace, 3"
        "$mod, 4, workspace, 4"
        "$mod, 5, workspace, 5"
        "$mod SHIFT, 1, movetoworkspace, 1"
        "$mod SHIFT, 2, movetoworkspace, 2"
        "$mod SHIFT, 3, movetoworkspace, 3"
        "$mod SHIFT, 4, movetoworkspace, 4"
        "$mod SHIFT, 5, movetoworkspace, 5"
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

  programs.kitty = {
    enable = true;
    settings = {
      confirm_os_window_close = 0;
      enable_audio_bell = false;
    };
  };

  programs.rofi = {
    enable = true;
    package = pkgs.rofi;
    terminal = "kitty";
    extraConfig = {
      modi = "drun,run,window";
      show-icons = true;
    };
  };
}
