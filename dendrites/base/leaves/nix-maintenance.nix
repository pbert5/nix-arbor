{ ... }:
{
  nix = {
    gc = {
      automatic = true;
      dates = "daily";
      randomizedDelaySec = "45m";
      persistent = true;
    };

    optimise = {
      automatic = true;
      dates = "weekly";
      randomizedDelaySec = "45m";
      persistent = true;
    };
  };
}
