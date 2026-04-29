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

  # True if a host carries any of the storage fabric roles.
  hasFabricRole =
    hostEntry: roles:
    lib.any (r: builtins.elem r (hostEntry.roles or [ ])) roles;

  # Return all hosts carrying a given role.
  hostsWithRole =
    inventory: role:
    lib.filterAttrs (_name: host: builtins.elem role (host.roles or [ ])) (inventory.hosts or { });

  # True when a URL uses only a private-overlay hostname (*-ygg suffix).
  isPrivateAnnexUrl =
    url:
    lib.hasPrefix "ssh://" url && (lib.hasSuffix "-ygg" (lib.removePrefix "ssh://" (lib.elemAt (lib.splitString "/" url) 0)));

  # Storage fabric defaults from site inventory (falls back gracefully).
  fabricDefaults =
    inventory:
    let
      fabric = inventory.storageFabric or { };
    in
    {
      transport = fabric.transport or {
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
    hasFabricRole
    hostsWithRole
    isPrivateAnnexUrl
    fabricDefaults
    ;
}
