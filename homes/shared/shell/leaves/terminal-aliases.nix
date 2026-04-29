{ config, ... }:
let
  cfg = config.flakeTarget;
in
{
  programs.fish.shellAbbrs = {
    ns = "sudo nixos-rebuild switch --flake ${cfg.path}#${cfg.hostName}";
    nb = "nix build ${cfg.path}#nixosConfigurations.${cfg.hostName}.config.system.build.toplevel --no-link";
    nf = "nix flake show ${cfg.path}";
  };
}
