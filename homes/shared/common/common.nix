{ config, lib, osConfig ? null, ... }:
{
  options.flakeTarget = {
    path = lib.mkOption {
      type = lib.types.str;
      default = "${config.home.homeDirectory}/flake";
      description = "Path to the flake checkout used by shell helper abbreviations.";
    };

    hostName = lib.mkOption {
      type = lib.types.str;
      default = if osConfig == null then "nixos" else osConfig.networking.hostName;
      description = "Host name targeted by local flake helper abbreviations.";
    };
  };

  config.programs.home-manager.enable = true;
}
