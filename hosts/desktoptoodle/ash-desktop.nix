{ lib, pkgs, ... }:
let
  obs-studio-nvenc = pkgs.obs-studio.override {
    cudaSupport = true;
  };
in
{
  home-manager.users.ash = {
    imports = [ ../../homes/shared/desktop-apps/desktop-apps.nix ];

    home.packages = with pkgs; [
      discord
      helvum
      obs-studio-nvenc
      pwvucontrol
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
  };
  
}
