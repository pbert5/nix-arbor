{ pkgs, ... }:
{
  imports = [
    ./leaves/neovim.nix
    ./leaves/zsh.nix
    ./leaves/starship.nix
    ./leaves/fzf.nix
    ./leaves/zoxide.nix
    ./leaves/atuin.nix
    ./leaves/navi.nix
    ./leaves/fastfetch.nix
    ./leaves/terminal-aliases.nix
  ];

  home.packages = with pkgs; [
    direnv
    fd
    ripgrep
  ];
}
