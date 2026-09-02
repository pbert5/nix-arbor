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
      message = "VS Code Remote-SSH requires nix-ld to be enabled";
    }
    {
      assertion = lib.elem pkgs.stdenv.cc.cc.lib config.programs.nix-ld.libraries;
      message = "VS Code Remote-SSH requires stdenv.cc.cc.lib for libstdc++.so.6";
    }
  ];
}
