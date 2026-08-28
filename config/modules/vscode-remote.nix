{
  config,
  lib,
  pkgs,
  ...
}:
{
  # Runtime evidence: VS Code Remote-SSH's bundled Node exited 127 and ldd
  # reported missing libstdc++.so.6. Keep this capability opt-in so ordinary
  # headless servers do not inherit nix-ld, and provide the C++ runtime it
  # actually needs.
  programs.nix-ld = {
    enable = true;
    libraries = [ pkgs.stdenv.cc.cc.lib ];
  };

  assertions = [
    {
      assertion = config.programs.nix-ld.enable;
      message = "r640 must keep nix-ld enabled for VS Code Remote-SSH";
    }
    {
      assertion = lib.elem pkgs.stdenv.cc.cc.lib config.programs.nix-ld.libraries;
      message = "r640 nix-ld must provide stdenv.cc.cc.lib for libstdc++.so.6";
    }
  ];
}
