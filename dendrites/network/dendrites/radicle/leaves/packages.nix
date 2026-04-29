{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    radicle-node
    radicle-httpd
    git
  ];
}
