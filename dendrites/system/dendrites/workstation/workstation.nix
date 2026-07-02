{ inputs, pkgs, ... }:
{
  imports = [
    ./leaves/diagnostics.nix
  ];

  networking.networkmanager.enable = true;
  virtualisation.docker = {
    enable = true;
    package = pkgs.docker_29;
  };

  hardware.keyboard.qmk.enable = true;
  services.udev.packages = [ pkgs.via ];

  environment.systemPackages = [
    inputs.nixard.packages.${pkgs.stdenv.hostPlatform.system}.default
  ];
}
