{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    git
    git-annex
    rsync
    openssh
  ];

  environment.etc."xdg/autostart/git-annex.desktop".text = ''
    [Desktop Entry]
    Type=Application
    Name=Git Annex Assistant
    Hidden=true
  '';
}
