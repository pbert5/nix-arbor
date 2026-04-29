{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    git
    git-annex
    rsync
    openssh
  ];
}
