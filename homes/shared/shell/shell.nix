{ pkgs, ... }:
{
  imports = [
    ./leaves/zsh.nix
    ./leaves/starship.nix
    ./leaves/fzf.nix
    ./leaves/zoxide.nix
    ./leaves/atuin.nix
    ./leaves/terminal-aliases.nix
  ];

  home.packages = with pkgs; [
    direnv
    fd
    ripgrep
  ];
}
