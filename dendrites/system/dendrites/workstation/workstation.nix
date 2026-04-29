{ config, ... }:
{
  networking.networkmanager.enable = true;
  virtualisation.docker.enable = true;
}
