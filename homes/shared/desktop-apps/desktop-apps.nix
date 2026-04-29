{ pkgs, ... }:
{
  home.packages = with pkgs; [
    file-roller
    gimp
    gnome-disk-utility
    google-chrome
    keepassxc
    pavucontrol
    vlc
    libreoffice-fresh
    hunspell
    hunspellDicts.en_US-large
  ];
}
