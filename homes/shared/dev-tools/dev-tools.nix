{ pkgs, ... }:
let
  unstablePkgs = if pkgs ? unstable then pkgs.unstable else pkgs;
in
{
  home.packages = with pkgs; [
    black
    jq
    mypy
    nil
    nixd
    nixfmt
    pyright
    python312
    python312Packages.ipython
    python312Packages.pip
    python312Packages.virtualenv
    ruff
    uv
    unstablePkgs.vscode
  ];
}
