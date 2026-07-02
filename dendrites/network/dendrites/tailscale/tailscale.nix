{ lib, hostInventory ? { }, ... }:
let
  operatorUsers = lib.attrByPath [ "org" "network" "tailscale" "operatorUsers" ] [ ] hostInventory;
in
{
  services.tailscale = {
    enable = true;
    useRoutingFeatures = lib.mkDefault "client";
    extraSetFlags = builtins.map (user: "--operator=${user}") operatorUsers;
  };
}
