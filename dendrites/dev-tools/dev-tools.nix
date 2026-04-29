{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    curl
    git
    ssh-import-id
    tailscale
    wget
    ripgrep
  ];
}
