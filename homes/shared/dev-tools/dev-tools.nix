{ pkgs, ... }:
let
  unstablePkgs = if pkgs ? unstable then pkgs.unstable else pkgs;
in
{
  programs.claude-code = {
    enable = true;
    package = unstablePkgs.claude-code;
  };

  programs.tmux = {
    enable = true;
    extraConfig = ''
      set -g mouse on
    '';
  };

  home.packages = with pkgs; [
    black
    jq
    mypy
    nh
    nil
    nixd
    nixfmt
    nix-search-cli
    pyright
    python312
    python312Packages.ipython
    python312Packages.pip
    python312Packages.virtualenv
    ruff
    uv
    unstablePkgs.vscode
    nmap
    rtk
    repomix
    # for serena
    typescript-language-server
    rust-analyzer
    gopls
  ];
}
