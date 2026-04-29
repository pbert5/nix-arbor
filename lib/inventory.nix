{ helpers, lib }:
let
  dendritesFromNetworks = networksInventory: selectedNetworks:
    lib.unique (
      helpers.removeNulls (
        builtins.map
          (networkName:
            let
              network = networksInventory.${networkName} or null;
            in
            if network == null then null else network.dendrite or null)
          selectedNetworks
      )
    );

  normalizeUser = userName: user:
    user
    // {
      roles = lib.unique (user.roles or [ ]);
      home =
        {
          homeModule = user.home.homeModule or userName;
        }
        // (user.home or { });
      org = user.org or { };
    };

  normalizeLegacyTape = host:
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
        cleanedFossilsafeSettings =
          legacyFossilsafeSettings
          // {
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
          fossilsafe =
            (builtins.removeAttrs legacyFossilsafe [ "settings" ])
            // {
              settings = cleanedFossilsafeSettings;
            };
          yatm =
            (builtins.removeAttrs legacyYatm [ "settings" ])
            // {
              settings = legacyYatmSettings;
            };
        };
      };

  normalizeLegacyZfs = host:
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

  normalizeHost = roles: networksInventory: hostName: host:
    let
      normalizedRoles =
        lib.unique (
          (host.roles or [ ])
          ++ helpers.removeNulls (builtins.map helpers.legacyRoleFromDendrite (host.dendrites or [ ]))
        );

      roleData = builtins.map (roleName: roles.${roleName} or { }) normalizedRoles;
      normalizedNetworks = lib.unique (host.networks or [ ]);
      networkDendrites = dendritesFromNetworks networksInventory normalizedNetworks;
      legacyZfs = normalizeLegacyZfs host;
      legacyTape = normalizeLegacyTape host;

      facts =
        lib.recursiveUpdate
          (
            lib.optionalAttrs (host ? hostId) {
              hostId = host.hostId;
            }
          )
          (
            lib.recursiveUpdate
              legacyZfs.facts
              (lib.recursiveUpdate legacyTape.facts (host.facts or { }))
          );

      org =
        lib.recursiveUpdate
          legacyZfs.org
          (lib.recursiveUpdate legacyTape.org (host.org or { }));
    in
    {
      exported = host.exported or true;
      system = host.system;
      roles = normalizedRoles;
      networks = normalizedNetworks;
      publicYggdrasil = host.publicYggdrasil or false;
      dendrites =
        lib.unique (
          helpers.removeNulls (builtins.map helpers.normalizeLegacyDendriteName (host.dendrites or [ ]))
          ++ networkDendrites
          ++ lib.concatMap (role: role.dendrites or [ ]) roleData
        );
      fruits =
        lib.unique (
          (host.fruits or [ ])
          ++ lib.concatMap (role: role.fruits or [ ]) roleData
        );
      users =
        lib.unique (
          (host.users or [ ])
          ++ lib.concatMap (role: role.users or [ ]) roleData
        );
      roleHomes = lib.unique (lib.concatMap (role: role.homes or [ ]) roleData);
      facts = facts;
      org = org;
      hardwareModules = host.hardwareModules or [ ];
      overrides =
        lib.unique (
          builtins.map
            helpers.normalizeOverrideName
            ((host.overrides or [ ]) ++ (host.hostModules or [ ]))
        );
      _sourceHostName = hostName;
    };
in
{
  normalizeInventory = rawInventory:
    let
      roles = rawInventory.roles or { };
      networks = rawInventory.networks or { };
      rawUsers =
        if rawInventory ? users then
          rawInventory.users
        else
          rawInventory.people or { };
      users =
        lib.mapAttrs
          normalizeUser
          rawUsers;
    in
    rawInventory
    // {
      inherit roles users networks;
      people = users;
      hosts = lib.mapAttrs (normalizeHost roles networks) (rawInventory.hosts or { });
    };
}
