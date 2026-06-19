{ pkgs, ... }:
{
  environment.systemPackages = [ pkgs.warpinator ];

  networking.firewall = {
    allowedTCPPorts = [
      42000 # transfers
      42001 # authentication
    ];
    # Current Warpinator releases use TCP. UDP 42000 retains compatibility
    # with clients older than 1.2.0.
    allowedUDPPorts = [ 42000 ];
  };
}
