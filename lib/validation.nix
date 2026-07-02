{
  endpoints,
  helpers,
  lib,
}:
let
  storageFabricValidation = import ./validation/storage-fabric.nix { inherit lib helpers; };
  formatFailures =
    prefix: failures: "${prefix}\n" + lib.concatMapStringsSep "\n" (message: "- ${message}") failures;

  buildInventoryValidations =
    {
      inventory,
      ...
    }:
    let
      availableUsers = builtins.attrNames inventory.users;
      availableHosts = builtins.attrNames inventory.hosts;
      availableNetworks = builtins.attrNames (inventory.networks or { });
      availableBootstrapHosts = builtins.attrNames (inventory.hostBootstrap or { });
      leaderKeysDir = ../inventory/keys/leaders;
      leaderKeyFiles = builtins.attrNames (
        lib.filterAttrs (name: type: type == "regular" && lib.hasSuffix ".txt" name) (
          builtins.readDir leaderKeysDir
        )
      );
      parseLeaderKeyHost =
        fileName:
        let
          matches = builtins.match "(.*)-root-deployer\\.txt" fileName;
        in
        if matches == null then null else builtins.elemAt matches 0;
      leaderKeyHosts = helpers.removeNulls (builtins.map parseLeaderKeyHost leaderKeyFiles);
      privateYggNodes = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" ] { } inventory;
      privateYggNetwork = lib.attrByPath [ "networks" "privateYggdrasil" ] { } inventory;
      guestAccess = inventory.guestAccess or { };
      guestNames = builtins.attrNames (guestAccess.guests or { });
      sshGuestGrants = lib.attrByPath [ "ssh" "grants" ] { } guestAccess;
      yggGuestGrants = lib.attrByPath [ "yggdrasil" "trustedGuests" ] { } guestAccess;
      networkValidationFailures = [ ];
      claimedPorts =
        builtins.map (endpoints.portOf 0) (builtins.attrValues (inventory.ports or { }))
        ++ builtins.map (endpoints.portOf 0) (builtins.attrValues (inventory.reservedPorts or { }));
      allowedTapeManagers = [
        "fossilsafe"
        "yatm"
      ];

      privateYggValidationFailures = lib.concatMap (
        nodeName:
        let
          node = privateYggNodes.${nodeName};
          peerHosts = node.peers or [ ];
          missingPeerHosts = helpers.missingFrom availableHosts peerHosts;
          missingPeerNodes = helpers.missingFrom (builtins.attrNames privateYggNodes) peerHosts;
        in
        lib.optionals (!(builtins.elem nodeName availableHosts)) [
          "inventory.networks.privateYggdrasil.nodes defines unknown host '${nodeName}'."
        ]
        ++ lib.optionals (missingPeerHosts != [ ]) [
          "inventory.networks.privateYggdrasil.nodes.${nodeName}.peers references unknown hosts: ${helpers.formatNames missingPeerHosts}."
        ]
        ++ lib.optionals (missingPeerNodes != [ ]) [
          "inventory.networks.privateYggdrasil.nodes.${nodeName}.peers references hosts without private Ygg node definitions: ${helpers.formatNames missingPeerNodes}."
        ]
      ) (builtins.attrNames privateYggNodes);
      bootstrapValidationFailures = lib.concatMap (
        hostName:
        let
          bootstrap = inventory.hostBootstrap.${hostName};
          transport = bootstrap.deploymentTransport or "bootstrap";
          yggAddress = lib.attrByPath [
            "networks"
            "privateYggdrasil"
            "nodes"
            hostName
            "address"
          ] null inventory;
          identityFile = bootstrap.identityFile or null;
          hasDatedKeyName = identityFile != null && builtins.match ".*_[0-9]{8}([^/]*)" identityFile != null;
          leaderKeyFile = "${hostName}-root-deployer.txt";
          operatorCapable = bootstrap.operatorCapable or false;
          host = inventory.hosts.${hostName} or { };
          install = bootstrap.install or null;
          installEnabled = install != null && (install.enable or false);
          hostInstall = lib.attrByPath [ "org" "install" ] { } host;
          installId = if install == null then null else install.installationId or null;
          hostInstallId = hostInstall.installationId or null;
          installDisks =
            if install == null then { } else lib.attrByPath [ "disko" "devices" "disk" ] { } install;
          expectedHardware = if install == null then { } else install.expectedHardware or { };
          expectedDiskSize = if install == null then { } else install.expectedDiskSize or { };
        in
        lib.optionals (!(builtins.elem hostName availableHosts)) [
          "inventory.hostBootstrap defines unknown host '${hostName}'."
        ]
        ++ lib.optionals (transport == "privateYggdrasil" && yggAddress == null) [
          "inventory.hostBootstrap.${hostName}.deploymentTransport is privateYggdrasil but inventory.networks.privateYggdrasil.nodes.${hostName}.address is not enrolled."
        ]
        ++ lib.optionals hasDatedKeyName [
          "inventory.hostBootstrap.${hostName}.identityFile '${identityFile}' contains a date-stamped filename. Use a stable key name so deployments survive machine transfers."
        ]
        ++ lib.optionals (operatorCapable && !(builtins.elem leaderKeyFile leaderKeyFiles)) [
          "inventory.hostBootstrap.${hostName}.operatorCapable is true but inventory/keys/leaders/${leaderKeyFile} is missing."
        ]
        ++ lib.optionals (installEnabled && !(hostInstall.enable or false)) [
          "inventory.hostBootstrap.${hostName}.install.enable requires hosts.${hostName}.org.install.enable."
        ]
        ++ lib.optionals (installEnabled && (installId == null || installId != hostInstallId)) [
          "inventory.hostBootstrap.${hostName}.install.installationId must match hosts.${hostName}.org.install.installationId."
        ]
        ++
          lib.optionals
            (
              installEnabled
              && (
                (install.targetHost or null) == null
                || (install.sshUser or null) == null
                || (install.expectedLiveHostName or null) == null
                || (install.expectedLiveMarker or null) == null
              )
            )
            [
              "inventory.hostBootstrap.${hostName}.install requires targetHost, sshUser, expectedLiveHostName, and expectedLiveMarker."
            ]
        ++
          lib.optionals
            (
              installEnabled
              && ((expectedHardware.sysVendor or null) == null || (expectedHardware.productName or null) == null)
            )
            [
              "inventory.hostBootstrap.${hostName}.install.expectedHardware requires sysVendor and productName."
            ]
        ++
          lib.optionals
            (
              installEnabled
              && (
                (expectedDiskSize.minimumBytes or null) == null || (expectedDiskSize.maximumBytes or null) == null
              )
            )
            [
              "inventory.hostBootstrap.${hostName}.install.expectedDiskSize requires minimumBytes and maximumBytes."
            ]
        ++ lib.optionals (installEnabled && builtins.length (builtins.attrNames installDisks) != 1) [
          "inventory.hostBootstrap.${hostName}.install.disko.devices.disk must define exactly one target disk."
        ]
      ) availableBootstrapHosts;
      leaderKeyValidationFailures = lib.concatMap (
        fileName:
        let
          keyHost = parseLeaderKeyHost fileName;
          bootstrap = inventory.hostBootstrap.${keyHost} or { };
        in
        lib.optionals (keyHost == null) [
          "inventory/keys/leaders/${fileName} does not follow the '<host>-root-deployer.txt' naming convention."
        ]
        ++ lib.optionals (keyHost != null && !(builtins.elem keyHost availableHosts)) [
          "inventory/keys/leaders/${fileName} references unknown host '${keyHost}'."
        ]
        ++ lib.optionals (keyHost != null && (bootstrap.operatorCapable or false) == false) [
          "inventory/keys/leaders/${fileName} exists but inventory.hostBootstrap.${keyHost}.operatorCapable is not true."
        ]
      ) leaderKeyFiles;
      guestAccessValidationFailures =
        let
          formatHostUsers =
            missingUsersByHost:
            lib.concatStringsSep "; " (
              lib.mapAttrsToList (hostName: users: "${hostName}: ${helpers.formatNames users}") (
                lib.filterAttrs (_hostName: users: users != [ ]) missingUsersByHost
              )
            );
        in
        lib.concatMap (
          grantName:
          let
            grant = sshGuestGrants.${grantName};
            missingHosts = helpers.missingFrom availableHosts (grant.hosts or [ ]);
            missingGuests = grant.missingGuestNames or helpers.missingFrom guestNames (grant.guests or [ ]);
            missingUsersByHost = grant.missingUsersByHost or { };
            hasMissingUsers = builtins.any (users: users != [ ]) (builtins.attrValues missingUsersByHost);
          in
          lib.optionals (missingHosts != [ ]) [
            "inventory.guestAccess.ssh.grants.${grantName} references unknown hosts: ${helpers.formatNames missingHosts}."
          ]
          ++ lib.optionals (missingGuests != [ ]) [
            "inventory.guestAccess.ssh.grants.${grantName} references unknown guests: ${helpers.formatNames missingGuests}."
          ]
          ++ lib.optionals ((grant.keys or [ ]) == [ ]) [
            "inventory.guestAccess.ssh.grants.${grantName} does not resolve to any SSH authorized keys."
          ]
          ++ lib.optionals hasMissingUsers [
            "inventory.guestAccess.ssh.grants.${grantName} references users that are not active on target hosts: ${formatHostUsers missingUsersByHost}."
          ]
        ) (builtins.attrNames sshGuestGrants)
        ++ lib.concatMap (
          grantName:
          let
            grant = yggGuestGrants.${grantName};
            missingHosts = helpers.missingFrom availableHosts (grant.hosts or [ ]);
            missingGuests = grant.missingGuestNames or helpers.missingFrom guestNames (grant.guests or [ ]);
            targetsWithPeerSourceFiltering = builtins.filter (
              hostName:
              lib.attrByPath [
                "networks"
                "privateYggdrasil"
                "nodes"
                hostName
                "firewall"
                "overlay"
                "restrictToPeerSources"
              ] false inventory
            ) (grant.hosts or [ ]);
          in
          lib.optionals (missingHosts != [ ]) [
            "inventory.guestAccess.yggdrasil.trustedGuests.${grantName} references unknown hosts: ${helpers.formatNames missingHosts}."
          ]
          ++ lib.optionals (missingGuests != [ ]) [
            "inventory.guestAccess.yggdrasil.trustedGuests.${grantName} references unknown guests: ${helpers.formatNames missingGuests}."
          ]
          ++ lib.optionals ((grant.publicKey or null) == null) [
            "inventory.guestAccess.yggdrasil.trustedGuests.${grantName} does not resolve to a Yggdrasil publicKey."
          ]
          ++ lib.optionals (targetsWithPeerSourceFiltering != [ ] && (grant.address or null) == null) [
            "inventory.guestAccess.yggdrasil.trustedGuests.${grantName} targets hosts with private Ygg peer-source filtering but does not resolve to an address: ${helpers.formatNames targetsWithPeerSourceFiltering}."
          ]
        ) (builtins.attrNames yggGuestGrants);
    in
    lib.optionals (!(builtins.length claimedPorts == builtins.length (lib.unique claimedPorts))) [
      "Duplicate port found in inventory.ports or inventory.reservedPorts."
    ]
    ++ lib.concatMap (
      hostName:
      let
        host = inventory.hosts.${hostName};
        missingUsers = helpers.missingFrom availableUsers (host.users or [ ]);
        missingNetworks = helpers.missingFrom availableNetworks (host.networks or [ ]);
        distributedBuildMachines = lib.attrByPath [ "org" "nix" "distributedBuilds" "builders" ] [ ] host;
        missingBuildMachines = helpers.missingFrom availableHosts distributedBuildMachines;
        tapeManager = lib.attrByPath [ "org" "storage" "tape" "manager" ] null host;
      in
      lib.optionals (missingUsers != [ ]) [
        "Host '${hostName}' references unknown users: ${helpers.formatNames missingUsers}."
      ]
      ++ lib.optionals (missingNetworks != [ ]) [
        "Host '${hostName}' references unknown networks: ${helpers.formatNames missingNetworks}."
      ]
      ++ lib.optionals (missingBuildMachines != [ ]) [
        "Host '${hostName}' references unknown distributed build machines: ${helpers.formatNames missingBuildMachines}."
      ]
      ++ lib.optionals (tapeManager != null && !(builtins.elem tapeManager allowedTapeManagers)) [
        "Host '${hostName}' has invalid org.storage.tape.manager '${tapeManager}'."
      ]
    ) (builtins.attrNames inventory.hosts)
    ++ privateYggValidationFailures
    ++ bootstrapValidationFailures
    ++ leaderKeyValidationFailures
    ++ guestAccessValidationFailures
    ++ networkValidationFailures
    ++ storageFabricValidation inventory;

  assertInventory =
    args:
    let
      failures = buildInventoryValidations args;
    in
    if failures == [ ] then
      null
    else
      throw (formatFailures "Dendritic inventory validation failed:" failures);

  buildCompositionValidations =
    {
      dendriteRegistry,
      fruitRegistry,
      host,
      hostName,
      inventory,
      resolvedDendrites,
      resolvedFruits,
      ...
    }:
    let
      dendriteEntries = builtins.map (name: dendriteRegistry.${name}) resolvedDendrites;
      fruitEntries = builtins.map (name: fruitRegistry.${name}) resolvedFruits;
      tapeDevices = lib.attrByPath [ "facts" "storage" "tape" "devices" ] null host;
      zfsConfig = lib.attrByPath [ "facts" "storage" "zfs" ] null host;
      bitlockerVolumes = lib.attrByPath [ "org" "storage" "bitlocker" "volumes" ] { } host;
      invalidBitlockerVolumes = builtins.filter (
        name:
        let
          volume = bitlockerVolumes.${name};
        in
        !(volume ? device && volume ? mountPoint && (volume.keyFiles or [ ]) != [ ])
      ) (builtins.attrNames bitlockerVolumes);
      tapeManager = lib.attrByPath [ "org" "storage" "tape" "manager" ] null host;
      privateYggNode = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" hostName ] null inventory;
      publicYggPeeringNode = lib.attrByPath [
        "networks"
        "publicYggdrasilPeering"
        "nodes"
        hostName
      ] null inventory;
      privateYggPeerHosts = if privateYggNode == null then [ ] else privateYggNode.peers or [ ];
      restrictToPeerSources = lib.attrByPath [
        "firewall"
        "overlay"
        "restrictToPeerSources"
      ] false privateYggNode;
      missingPeerAddresses = builtins.filter (
        peerHost:
        (lib.attrByPath [ "networks" "privateYggdrasil" "nodes" peerHost "address" ] null inventory) == null
      ) privateYggPeerHosts;
      missingPeerPublicKeys = builtins.filter (
        peerHost:
        (lib.attrByPath [ "networks" "privateYggdrasil" "nodes" peerHost "publicKey" ] null inventory)
        == null
      ) privateYggPeerHosts;
    in
    lib.concatMap (
      entry:
      let
        conflicts = builtins.filter (name: builtins.elem name resolvedDendrites) (
          entry.meta.conflicts or [ ]
        );
      in
      lib.optionals (conflicts != [ ]) [
        "Host '${hostName}' selects dendrite '${entry.meta.name}' which conflicts with ${helpers.formatNames conflicts}."
      ]
    ) dendriteEntries
    ++ lib.concatMap (
      entry:
      let
        required = builtins.filter (name: !(builtins.elem name resolvedDendrites)) (
          entry.meta.requiresDendrites or [ ]
        );
      in
      lib.optionals (required != [ ]) [
        "Host '${hostName}' selects fruit '${entry.meta.name}' without required dendrites ${helpers.formatNames required}."
      ]
    ) fruitEntries
    ++
      lib.optionals
        (
          builtins.elem "storage/zfs" resolvedDendrites
          && (zfsConfig == null || !(zfsConfig ? poolName) || !(zfsConfig ? rootMountPoint))
        )
        [
          "Host '${hostName}' selects storage/zfs but is missing facts.storage.zfs.poolName or facts.storage.zfs.rootMountPoint."
        ]
    ++
      lib.optionals
        (
          builtins.elem "storage/tape" resolvedDendrites
          && (
            tapeDevices == null
            || !(tapeDevices ? changer)
            || !((tapeDevices ? drive) || (tapeDevices ? drives && tapeDevices.drives != [ ]))
          )
        )
        [
          "Host '${hostName}' selects storage/tape but is missing facts.storage.tape.devices.changer and at least one drive."
        ]
    ++ lib.optionals (builtins.elem "storage/bitlocker" resolvedDendrites && bitlockerVolumes == { }) [
      "Host '${hostName}' selects storage/bitlocker but is missing org.storage.bitlocker.volumes."
    ]
    ++
      lib.optionals
        (builtins.elem "storage/bitlocker" resolvedDendrites && invalidBitlockerVolumes != [ ])
        [
          "Host '${hostName}' selects storage/bitlocker but these volumes are missing device, mountPoint, or keyFiles: ${helpers.formatNames invalidBitlockerVolumes}."
        ]
    ++
      lib.optionals
        (
          builtins.elem "storage/tape" resolvedDendrites
          && tapeManager == "fossilsafe"
          && !(builtins.elem "fossilsafe" resolvedFruits)
        )
        [
          "Host '${hostName}' selects the FossilSafe tape manager but does not attach the fossilsafe fruit."
        ]
    ++
      lib.optionals
        (builtins.elem "network/yggdrasil-public-peering" resolvedDendrites && publicYggPeeringNode == null)
        [
          "Host '${hostName}' selects network/yggdrasil-public-peering but is missing inventory.networks.publicYggdrasilPeering.nodes.${hostName}."
        ]
    ++
      lib.optionals
        (builtins.elem "network/yggdrasil-private" resolvedDendrites && privateYggNode == null)
        [
          "Host '${hostName}' selects network/yggdrasil-private but is missing inventory.networks.privateYggdrasil.nodes.${hostName}."
        ]
    ++ lib.optionals (restrictToPeerSources && missingPeerAddresses != [ ]) [
      "Host '${hostName}' enables private Ygg peer-source filtering but peers are missing inventory.networks.privateYggdrasil.nodes.<peer>.address: ${helpers.formatNames missingPeerAddresses}."
    ]
    ++ lib.optionals (restrictToPeerSources && missingPeerPublicKeys != [ ]) [
      "Host '${hostName}' enables private Ygg peer-source filtering but peers are missing inventory.networks.privateYggdrasil.nodes.<peer>.publicKey: ${helpers.formatNames missingPeerPublicKeys}."
    ];

  assertComposition =
    args:
    let
      failures = buildCompositionValidations args;
    in
    if failures == [ ] then
      null
    else
      throw (formatFailures "Dendritic composition validation failed:" failures);
in
{
  inherit
    assertComposition
    assertInventory
    buildCompositionValidations
    buildInventoryValidations
    ;
}
