{ inputs, pkgs, ... }:
{
  environment.systemPackages = [
    inputs.agenix.packages.${pkgs.stdenv.hostPlatform.system}.default
    pkgs.sops
    pkgs.ssh-to-age
  ];
}
