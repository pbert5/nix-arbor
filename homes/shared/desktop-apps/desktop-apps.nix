{ lib, pkgs, ... }:
{
  # Override imv's upstream desktop file which has NoDisplay=true, making it
  # invisible in KDE's open-with dialog. This local entry makes it selectable.
  xdg.desktopEntries.imv = {
    name = "imv";
    genericName = "Image Viewer";
    exec = "imv %F";
    terminal = false;
    categories = [
      "Graphics"
      "2DGraphics"
      "Viewer"
    ];
    mimeType = [
      "image/jpeg"
      "image/png"
      "image/gif"
      "image/webp"
      "image/bmp"
      "image/tiff"
      "image/svg+xml"
      "image/x-farbfeld"
      "image/heif"
      "image/avif"
      "image/jxl"
    ];
  };

  xdg.desktopEntries.google-chrome = {
    name = "Google Chrome";
    genericName = "Web Browser";
    exec = "${lib.getExe pkgs.google-chrome} --new-window %U";
    icon = "google-chrome";
    terminal = false;
    categories = [
      "Network"
      "WebBrowser"
    ];
    mimeType = [
      "text/html"
      "text/xml"
      "application/xhtml+xml"
      "application/xml"
      "application/rss+xml"
      "application/rdf+xml"
      "image/gif"
      "image/jpeg"
      "image/png"
      "image/webp"
      "x-scheme-handler/http"
      "x-scheme-handler/https"
    ];
  };

  home.packages = with pkgs; [
    file-roller
    gimp
    anki-bin
    gnome-disk-utility
    google-chrome
    keepassxc
    pavucontrol
    imv
    vlc
    libreoffice-fresh
    hunspell
    hunspellDicts.en_US-large
  ];
}
