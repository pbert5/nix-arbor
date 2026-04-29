{ lib, site, hostInventory, ... }:
let
  fabric = site.storageFabric or { };
  radicleOrg = lib.attrByPath [ "org" "network" "radicle" ] { } hostInventory;
  isSeed = builtins.elem "radicle-seed" (hostInventory.roles or [ ]);
  repos = radicleOrg.repos or (fabric.radicle.repos or [ ]);
in
lib.mkIf isSeed {
  # Seed nodes persist repo data and serve peers.
  # Repo list is sourced from org.network.radicle.repos or storageFabric.radicle.repos.
  environment.etc."radicle/seed-repos.json".text = builtins.toJSON { inherit repos; };
}
