{ pkgs, ... }:
let
  unstablePkgs = if pkgs ? unstable then pkgs.unstable else pkgs;
in
{
  programs.atuin = {
    enable = true;
    enableFishIntegration = true;
    package = unstablePkgs.atuin;
    settings = {
      auto_sync = false;
      update_check = false;
      search_mode = "fuzzy";
      filter_mode = "global";
      enter_accept = true;
    };
  };
}
