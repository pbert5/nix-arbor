{ pkgs, ... }:
{
  environment.systemPackages = with pkgs; [
    vulnix
    sbomnix
    grype
    lynis
    nix-tree
    nix-du
    nix-output-monitor
  ];
}
