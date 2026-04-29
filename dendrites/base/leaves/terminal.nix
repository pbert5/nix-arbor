{ ... }:
{
  programs.fish.enable = true;
  environment.extraOutputsToInstall = [ "man" ];
}
