{ lib, pkgs, ... }:
let
  obs-studio-nvenc = pkgs.obs-studio.override {
    cudaSupport = true;
  };
  installJDownloader = pkgs.writeShellScript "install-jdownloader-flatpak" ''
    set -euo pipefail

    ${lib.getExe pkgs.flatpak} --user remote-add --if-not-exists \
      flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    ${lib.getExe pkgs.flatpak} --user install --noninteractive --or-update \
      flathub org.jdownloader.JDownloader
  '';
in
{
  services.flatpak.enable = true;

  home-manager.users.ash = {
    imports = [ ../../homes/shared/desktop-apps/desktop-apps.nix ];

    home.packages = with pkgs; [
      discord
      crosspipe
      obs-studio-nvenc
      pwvucontrol
      via

    ];

    gtk.enable = true;
    gtk.gtk4.theme = null;
    gtk.colorScheme = "dark";
    gtk.iconTheme = {
      package = pkgs.papirus-icon-theme;
      name = "Papirus";
    };

    home.pointerCursor = {
      package = lib.mkDefault pkgs.adwaita-icon-theme;
      name = "Adwaita";
      size = 24;
      gtk.enable = true;
      x11.enable = true;
    };

    dconf.settings = {
      "org/gnome/desktop/interface" = {
        clock-format = "12h";
        color-scheme = "prefer-dark";
      };

      "org/gnome/mutter" = {
        experimental-features = [ ];
      };
    };

    programs.git.settings.user = {
      email = "user@example.com";
      name = "ash-desktoptoodle";
    };

    xdg.desktopEntries.jdownloader = {
      name = "JDownloader";
      comment = "Download management tool";
      exec = "${lib.getExe pkgs.flatpak} run org.jdownloader.JDownloader";
      icon = "org.jdownloader.JDownloader";
      categories = [ "Network" ];
      terminal = false;
    };

    systemd.user.services.jdownloader-flatpak-install = {
      Unit.Description = "Ensure JDownloader is installed from Flathub";
      Service = {
        Type = "oneshot";
        ExecStart = installJDownloader;
        RemainAfterExit = true;
      };
      Install.WantedBy = [ "default.target" ];
    };
  };

}
