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
      availableRoles = builtins.attrNames inventory.roles;
      availableUsers = builtins.attrNames inventory.users;
      availableHosts = builtins.attrNames inventory.hosts;
      availableNetworks = builtins.attrNames (inventory.networks or { });
      availableBootstrapHosts = builtins.attrNames (inventory.hostBootstrap or { });
      privateYggNodes = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" ] { } inventory;
      privateYggNetwork = lib.attrByPath [ "networks" "privateYggdrasil" ] { } inventory;
      networkValidationFailures = lib.concatMap (
        networkName:
        let
          network = inventory.networks.${networkName};
          dendrite = network.dendrite or null;
        in
        lib.optionals (dendrite == null) [
          "inventory.networks.${networkName} is missing a dendrite declaration."
        ]
      ) availableNetworks;
      claimedPorts =
        builtins.map (endpoints.portOf 0) (builtins.attrValues (inventory.ports or { }))
        ++ builtins.map (endpoints.portOf 0) (builtins.attrValues (inventory.reservedPorts or { }));
      allowedTapeManagers = [
        "fossilsafe"
        "tapelib"
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
      ) availableBootstrapHosts;
    in
    lib.optionals (!(builtins.length claimedPorts == builtins.length (lib.unique claimedPorts))) [
      "Duplicate port found in inventory.ports or inventory.reservedPorts."
    ]
    ++ lib.concatMap (
      userName:
      let
        user = inventory.users.${userName};
        missingRoles = helpers.missingFrom availableRoles (user.roles or [ ]);
      in
      lib.optionals (missingRoles != [ ]) [
        "User '${userName}' references unknown roles: ${helpers.formatNames missingRoles}."
      ]
    ) availableUsers
    ++ lib.concatMap (
      hostName:
      let
        host = inventory.hosts.${hostName};
        missingUsers = helpers.missingFrom availableUsers (host.users or [ ]);
        missingRoles = helpers.missingFrom availableRoles (host.roles or [ ]);
        missingNetworks = helpers.missingFrom availableNetworks (host.networks or [ ]);
        distributedBuildMachines = lib.attrByPath [ "org" "nix" "distributedBuilds" "builders" ] [ ] host;
        missingBuildMachines = helpers.missingFrom availableHosts distributedBuildMachines;
        tapeManager = lib.attrByPath [ "org" "storage" "tape" "manager" ] null host;
      in
      lib.optionals (missingUsers != [ ]) [
        "Host '${hostName}' references unknown users: ${helpers.formatNames missingUsers}."
      ]
      ++ lib.optionals (missingRoles != [ ]) [
        "Host '${hostName}' references unknown roles: ${helpers.formatNames missingRoles}."
      ]
      ++ lib.optionals (missingNetworks != [ ]) [
        "Host '${hostName}' references unknown networks: ${helpers.formatNames missingNetworks}."
      ]
      ++ lib.optionals (missingBuildMachines != [ ]) [
        "Host '${hostName}' references unknown distributed build machines: ${helpers.formatNames missingBuildMachines}."
      ]
      ++ lib.optionals ((host.publicYggdrasil or false) && !(privateYggNetwork.public or false)) [
        "Host '${hostName}' opts into publicYggdrasil but inventory.networks.privateYggdrasil.public is disabled."
      ]
      ++ lib.optionals (tapeManager != null && !(builtins.elem tapeManager allowedTapeManagers)) [
        "Host '${hostName}' has invalid org.storage.tape.manager '${tapeManager}'."
      ]
    ) (builtins.attrNames inventory.hosts)
    ++ privateYggValidationFailures
    ++ bootstrapValidationFailures
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
      hostRoles = host.roles or [ ];
      tapeManager = lib.attrByPath [ "org" "storage" "tape" "manager" ] null host;
      privateYggNode = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" hostName ] null inventory;
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
        classes = entry.meta.hostClasses or [ ];
      in
      lib.optionals (conflicts != [ ]) [
        "Host '${hostName}' selects dendrite '${entry.meta.name}' which conflicts with ${helpers.formatNames conflicts}."
      ]
      ++ lib.optionals (classes != [ ] && lib.intersectLists classes hostRoles == [ ]) [
        "Host '${hostName}' selects dendrite '${entry.meta.name}' but its roles ${helpers.formatNames hostRoles} do not match supported host classes ${helpers.formatNames classes}."
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
        (
          builtins.elem "storage/tape" resolvedDendrites
          && tapeManager == "tapelib"
          && !(builtins.elem "tapelib" resolvedFruits)
        )
        [
          "Host '${hostName}' selects the tapelib tape manager but does not attach the tapelib fruit."
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
