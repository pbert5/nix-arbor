{ pkgs, ... }:
{
  # VS Code Remote-SSH's bundled Node is not a Nix-built binary. Keep this
  # capability opt-in so ordinary headless servers do not inherit nix-ld.
  programs.nix-ld = {
    enable = true;
    libraries = [ pkgs.stdenv.cc.cc.lib ];
  };
}
