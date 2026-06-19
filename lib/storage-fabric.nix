{ lib }:
let
  # Resolve the Yggdrasil address for a host from the inventory.
  yggAddressOf =
    inventory: hostName:
    lib.attrByPath [
      "networks"
      "privateYggdrasil"
      "nodes"
      hostName
      "address"
    ] null inventory;

  # True if a host carries any of the storage fabric capabilities.
  hasFabricCapability =
    hostEntry: capabilities:
    let
      annex = lib.attrByPath [ "org" "storage" "annex" "fabric" ] { } hostEntry;
      seaweedfs = lib.attrByPath [ "org" "storage" "seaweedfs" ] { } hostEntry;
      observability = lib.attrByPath [ "org" "storage" "observability" "enable" ] false hostEntry;
      radicleSeed = lib.attrByPath [ "org" "network" "radicle" "seed" ] false hostEntry;
      capabilitySet = [
        {
          name = "archive-node";
          enabled = annex.archive or false;
        }
        {
          name = "annex-storage";
          enabled = annex.storage or false;
        }
        {
          name = "annex-client";
          enabled = annex.client or false;
        }
        {
          name = "annex-workstation";
          enabled = annex.workstation or false;
        }
        {
          name = "annex-compute-cache";
          enabled = annex.computeCache or false;
        }
        {
          name = "seaweed-master";
          enabled = seaweedfs.master or false;
        }
        {
          name = "seaweed-volume";
          enabled = seaweedfs.volume or false;
        }
        {
          name = "seaweed-filer";
          enabled = seaweedfs.filer or false;
        }
        {
          name = "seaweed-s3";
          enabled = seaweedfs.s3 or false;
        }
        {
          name = "radicle-seed";
          enabled = radicleSeed;
        }
        {
          name = "storage-fabric-observer";
          enabled = observability;
        }
      ];
      active = builtins.map (capability: capability.name) (
        builtins.filter (capability: capability.enabled) capabilitySet
      );
    in
    lib.any (capability: builtins.elem capability active) capabilities;

  # Return all hosts carrying a given storage fabric capability.
  hostsWithCapability =
    inventory: capability:
    lib.filterAttrs (_name: host: hasFabricCapability host [ capability ]) (inventory.hosts or { });

  # True when a URL uses only a private-overlay hostname (*-ygg suffix).
  isPrivateAnnexUrl =
    url:
    lib.hasPrefix "ssh://" url
    && (lib.hasSuffix "-ygg" (lib.removePrefix "ssh://" (lib.elemAt (lib.splitString "/" url) 0)));

  # Storage fabric defaults from site inventory (falls back gracefully).
  fabricDefaults =
    inventory:
    let
      fabric = inventory.storageFabric or { };
    in
    {
      transport =
        fabric.transport or {
          privateNetwork = "privateYggdrasil";
          allowPublicContentTransfers = false;
        };
      annexRepoRoot = lib.attrByPath [ "annex" "repoRoot" ] "/srv/annex/cluster-data" fabric;
      annexUser = lib.attrByPath [ "annex" "user" ] "annex" fabric;
      annexGroup = lib.attrByPath [ "annex" "group" ] "annex" fabric;
      numCopies = lib.attrByPath [ "annex" "defaultNumCopies" ] 2 fabric;
      seaweedfsEnabled = lib.attrByPath [ "seaweedfs" "hotPool" "enable" ] false fabric;
      radicleEnabled = lib.attrByPath [ "radicle" "enable" ] false fabric;
    };
in
{
  inherit
    yggAddressOf
    hasFabricCapability
    hostsWithCapability
    isPrivateAnnexUrl
    fabricDefaults
    ;
}
