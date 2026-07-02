{ helpers, lib }:
let
  accessLib = import ./access.nix { inherit helpers lib; };
  identityPolicyLib = import ./identity-policy.nix { inherit lib; };
  yggIdentitiesLib = import ./yggdrasil-identities.nix { };

  mergeAttrsList = attrs: lib.foldl' lib.recursiveUpdate { } attrs;

  normalizeNetworks =
    rawNetworks:
    let
      collectLayer =
        path: inheritedOptions: layer:
        let
          layerOptions = lib.recursiveUpdate inheritedOptions (layer.options or { });
          directNetworks = lib.mapAttrs (
            networkName: network:
            network
            // {
              name = network.name or networkName;
              path = path ++ [ networkName ];
              options = lib.recursiveUpdate layerOptions (network.options or { });
            }
          ) (layer.networks or { });
          childNetworks = mergeAttrsList (
            lib.mapAttrsToList (
              layerName: childLayer: collectLayer (path ++ [ layerName ]) layerOptions childLayer
            ) (layer.layers or { })
          );
        in
        directNetworks // childNetworks;
    in
    if rawNetworks ? layers then collectLayer [ ] { } { layers = rawNetworks.layers; } else rawNetworks;

  dendritesFromNetworks =
    networksInventory: selectedNetworks:
    lib.unique (
      helpers.removeNulls (
        builtins.map (
          networkName:
          let
            network = networksInventory.${networkName} or null;
          in
          if network == null then null else network.dendrite or null
        ) selectedNetworks
      )
    );

  enabledNetworkNames =
    networksInventory:
    builtins.attrNames (lib.filterAttrs (_: network: network.enabled or true) networksInventory);

  normalizeNetworkMembership =
    networksInventory: org: host:
    let
      membership = lib.attrByPath [ "network" "membership" ] { } org;
      optIn =
        if membership ? optIn then
          membership.optIn
        else if host ? networks then
          host.networks
        else
          "all";
      selected =
        if optIn == "all" then
          enabledNetworkNames networksInventory
        else if builtins.isList optIn then
          optIn
        else
          [ optIn ];
      optOut = membership.optOut or [ ];
    in
    lib.unique (builtins.filter (networkName: !(builtins.elem networkName optOut)) selected);

  normalizeUser =
    userName: user:
    user
    // {
      home = {
        homeModule = user.home.homeModule or userName;
      }
      // (user.home or { });
      org = user.org or { };
    };

  normalizeLegacyTape =
    host:
    let
      legacyTape = host.tapeLibrary or null;
    in
    if legacyTape == null then
      {
        facts = { };
        org = { };
      }
    else
      let
        legacyFossilsafe = legacyTape.fossilsafe or { };
        legacyFossilsafeSettings = legacyFossilsafe.settings or { };
        legacyTapeSettings = legacyFossilsafeSettings.tape or { };
        legacyDrives =
          if legacyTapeSettings ? drive_devices then
            legacyTapeSettings.drive_devices
          else if legacyTapeSettings ? drive_device then
            [ legacyTapeSettings.drive_device ]
          else
            [ ];
        legacyDrive =
          if legacyTapeSettings ? drive_device then
            legacyTapeSettings.drive_device
          else
            helpers.firstOrNull legacyDrives;
        cleanedFossilsafeSettings = legacyFossilsafeSettings // {
          tape = builtins.removeAttrs legacyTapeSettings [
            "changer_device"
            "drive_device"
            "drive_devices"
          ];
        };
        legacyYatm = legacyTape.yatm or { };
        legacyYatmSettings = builtins.removeAttrs (legacyYatm.settings or { }) [ "tape_devices" ];
      in
      {
        facts = lib.optionalAttrs (legacyTapeSettings != { }) {
          storage.tape.devices =
            (lib.optionalAttrs (legacyTapeSettings ? changer_device) {
              changer = legacyTapeSettings.changer_device;
            })
            // (lib.optionalAttrs (legacyDrive != null) { drive = legacyDrive; })
            // (lib.optionalAttrs (legacyDrives != [ ]) { drives = legacyDrives; });
        };

        org.storage.tape = {
          manager = legacyTape.ltfsManager or "fossilsafe";
          fossilsafe = (builtins.removeAttrs legacyFossilsafe [ "settings" ]) // {
            settings = cleanedFossilsafeSettings;
          };
          yatm = (builtins.removeAttrs legacyYatm [ "settings" ]) // {
            settings = legacyYatmSettings;
          };
        };
      };

  normalizeLegacyZfs =
    host:
    let
      legacyZfs = host.zfsPool or null;
    in
    if legacyZfs == null then
      {
        facts = { };
        org = { };
      }
    else
      {
        facts.storage.zfs = {
          poolName = legacyZfs.poolName;
          rootMountPoint = legacyZfs.rootMountPoint;
        };

        org = lib.optionalAttrs (legacyZfs ? linkedUsers) {
          storage.zfs.linkedUsers = legacyZfs.linkedUsers;
        };
      };

  normalizeHost =
    networksInventory: hostName: host:
    let
      legacyZfs = normalizeLegacyZfs host;
      legacyTape = normalizeLegacyTape host;

      facts = lib.recursiveUpdate (lib.optionalAttrs (host ? hostId) {
        hostId = host.hostId;
      }) (lib.recursiveUpdate legacyZfs.facts (lib.recursiveUpdate legacyTape.facts (host.facts or { })));

      org = lib.recursiveUpdate legacyZfs.org (lib.recursiveUpdate legacyTape.org (host.org or { }));
      normalizedNetworks = normalizeNetworkMembership networksInventory org host;
      networkDendrites = dendritesFromNetworks networksInventory normalizedNetworks;
    in
    {
      exported = host.exported or true;
      system = host.system;
      networks = normalizedNetworks;
      dendrites = lib.unique (
        helpers.removeNulls (builtins.map helpers.normalizeLegacyDendriteName (host.dendrites or [ ]))
        ++ networkDendrites
      );
      fruits = lib.unique (host.fruits or [ ]);
      users = lib.unique (host.users or [ ]);
      facts = facts;
      org = org;
      hardwareModules = host.hardwareModules or [ ];
      overrides = lib.unique (
        builtins.map helpers.normalizeOverrideName ((host.overrides or [ ]) ++ (host.hostModules or [ ]))
      );
      _sourceHostName = hostName;
    };
  mergeYggIdentitiesIntoNetworks =
    networks: yggdrasilServices:
    let
      yggIdentities = yggIdentitiesLib.deriveYggdrasilIdentities yggdrasilServices;
    in
    if !(networks ? privateYggdrasil) then
      networks
    else
      networks
      // {
        privateYggdrasil = networks.privateYggdrasil // {
          nodes = lib.mapAttrs (
            nodeName: node: node // (yggIdentities.${nodeName} or { })
          ) (networks.privateYggdrasil.nodes or { });
        };
      };

in
{
  normalizeInventory =
    rawInventory:
    let
      rawNetworks = rawInventory.networks or { };
      networks = normalizeNetworks rawNetworks;
      rawUsers = if rawInventory ? users then rawInventory.users else rawInventory.people or { };
      users = lib.mapAttrs normalizeUser rawUsers;
      yggdrasilServices = (rawInventory.identities or { }).services.yggdrasil or { };
      networksWithYgg = mergeYggIdentitiesIntoNetworks networks yggdrasilServices;
      hosts = lib.mapAttrs (normalizeHost networksWithYgg) (rawInventory.hosts or { });
      guestAccess = accessLib.normalizeGuestAccess {
        inherit hosts users;
        rawAccess = rawInventory.guestAccess or { };
      };
    in
    rawInventory
    // {
      inherit guestAccess;
      inherit users;
      networks = networksWithYgg;
      networkTopology = rawNetworks;
      people = users;
      inherit hosts;
      identityPolicy = identityPolicyLib.normalizeIdentityPolicy rawInventory;
    };
}
