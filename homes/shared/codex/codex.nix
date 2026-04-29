{ pkgs, ... }:
let
  unstablePkgs = if pkgs ? unstable then pkgs.unstable else pkgs;
in
{
  programs.codex = {
    enable = true;
    package = unstablePkgs.codex;
  };
}
