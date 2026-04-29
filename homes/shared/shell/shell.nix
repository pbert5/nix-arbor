{ pkgs, ... }:
{
  imports = [
    ./leaves/fish.nix
    ./leaves/starship.nix
    ./leaves/fzf.nix
    ./leaves/zoxide.nix
    ./leaves/atuin.nix
    ./leaves/terminal-aliases.nix
  ]; #TODO: in the handeling of a dendrite, if we import the dendrite the leaves should be imported automatically so we dont have to remember to import each leaf here, and if we want to use a leaf in multiple dendrites we can just import it in each dendrite that needs it, but the leaf will only actually be imported once

  home.packages = with pkgs; [
    direnv
    fd
    ripgrep
  ];
}
