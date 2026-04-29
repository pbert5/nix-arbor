{ lib, helpers }:
# Storage fabric validation checks.
# Called from lib/validation.nix as part of the full inventory validation pass.
#
# Returns a list of failure message strings (empty = valid).
inventory:
let
  fabric = inventory.storageFabric or null;
  hosts = inventory.hosts or { };
  transport = if fabric == null then { } else fabric.transport or { };
  privateNetwork = transport.privateNetwork or "privateYggdrasil";
  allowPublicTransfers = transport.allowPublicContentTransfers or false;
  privateYggNodes = lib.attrByPath [ "networks" privateNetwork "nodes" ] { } inventory;
  hotPool = lib.attrByPath [ "seaweedfs" "hotPool" ] { } fabric;
  replication = hotPool.replication or "000";
  hotPoolEnabled = hotPool.enable or false;
  masterHosts = lib.filter (h: hostHasRole h "seaweed-master") (builtins.attrNames hosts);
  filerHosts = lib.filter (h: hostHasRole h "seaweed-filer") (builtins.attrNames hosts);

  # Helpers
  hostHasRole = hostName: role: builtins.elem role ((hosts.${hostName} or { }).roles or [ ]);

  hostOnPrivateYgg = hostName: builtins.hasAttr hostName privateYggNodes;

  hostPrivateYggAddress = hostName: lib.attrByPath [ hostName "address" ] null privateYggNodes;

  hostPrivateYggPublicKey = hostName: lib.attrByPath [ hostName "publicKey" ] null privateYggNodes;

  archiveFabricRoles = [
    "archive-node"
    "annex-storage"
    "annex-client"
    "annex-workstation"
    "annex-compute-cache"
    "seaweed-master"
    "seaweed-volume"
    "seaweed-filer"
    "seaweed-s3"
    "radicle-seed"
    "storage-fabric-observer"
  ];
  allFabricHosts = lib.filter (h: lib.any (r: hostHasRole h r) archiveFabricRoles) (
    builtins.attrNames hosts
  );
  seaweedRoles = [
    "seaweed-master"
    "seaweed-volume"
    "seaweed-filer"
    "seaweed-s3"
  ];
  seaweedHosts = lib.filter (h: lib.any (r: hostHasRole h r) seaweedRoles) (builtins.attrNames hosts);
  seaweedVolumeHosts = lib.filter (h: hostHasRole h "seaweed-volume") (builtins.attrNames hosts);
  isAbsolutePath = path: builtins.isString path && lib.hasPrefix "/" path;

  # M11: A URL is considered a disallowed content remote if it starts with a
  # known metadata-only prefix.
  isMetadataOnlyRemote =
    url:
    lib.any (prefix: lib.hasPrefix prefix url) [
      "https://github.com"
      "user@example.com"
      "rad://"
      "https://radicle"
    ];

  looksPrivateEndpoint =
    url:
    lib.any (needle: lib.hasInfix needle url) [
      "-ygg"
      ".ygg"
      ".internal"
      "localhost"
      "127.0.0.1"
      "::1"
    ];

  isPublicContentRemote = url: !allowPublicTransfers && url != "" && !(looksPrivateEndpoint url);

  tapeFacts = host: lib.attrByPath [ "facts" "storage" "tape" "devices" ] { } host;

  hasTapeFacts =
    host:
    let
      devices = tapeFacts host;
    in
    (devices ? changer) && ((devices ? drive) || (devices ? drives && devices.drives != [ ]));

  digitToInt =
    digit:
    {
      "0" = 0;
      "1" = 1;
      "2" = 2;
      "3" = 3;
      "4" = 4;
      "5" = 5;
      "6" = 6;
      "7" = 7;
      "8" = 8;
      "9" = 9;
    }
    .${digit};
  replicationDigits = builtins.match "([0-9])([0-9])([0-9])" replication;
  replicationCopies =
    if replicationDigits == null then
      null
    else
      1 + lib.foldl' (sum: digit: sum + digitToInt digit) 0 replicationDigits;

  # Check declared annex remotes in org.storage.annex.remotes (optional,
  # per-host).  Each entry is { name, url }.
  checkAnnexRemoteUrls =
    hostName:
    let
      remotes = lib.attrByPath [ "org" "storage" "annex" "remotes" ] [ ] (hosts.${hostName} or { });
    in
    lib.concatMap (
      remote:
      lib.optionals (isMetadataOnlyRemote (remote.url or "")) [
        "Host '${hostName}' declares annex remote '${remote.name or "?"}' with URL '${remote.url or ""}' which is a metadata-only remote.  Annex content must not flow over public Git or Radicle remotes."
      ]
      ++ lib.optionals (isPublicContentRemote (remote.url or "")) [
        "Host '${hostName}' declares annex remote '${remote.name or "?"}' with URL '${remote.url or ""}' which does not look private.  Annex content remotes must use private Ygg aliases or explicitly private endpoints."
      ]
    ) remotes;

in
if fabric == null || !(fabric.enable or true) then
  [ ]
else
  lib.optionals allowPublicTransfers [
    "storageFabric.transport.allowPublicContentTransfers is true.  Public content transfers are rejected by default; keep this false for the private storage fabric."
  ]
  ++ lib.optionals (hotPoolEnabled && !isAbsolutePath (hotPool.mountPoint or "/hot")) [
    "storageFabric.seaweedfs.hotPool.mountPoint must be an absolute path."
  ]
  ++ lib.optionals (hotPoolEnabled && !isAbsolutePath (hotPool.filerPath or "/srv/seaweedfs/filer")) [
    "storageFabric.seaweedfs.hotPool.filerPath must be an absolute path."
  ]
  ++
    lib.optionals (hotPoolEnabled && !isAbsolutePath (hotPool.volumePath or "/srv/seaweedfs/volumes"))
      [
        "storageFabric.seaweedfs.hotPool.volumePath must be an absolute path."
      ]
  ++ lib.optionals (hotPoolEnabled && masterHosts == [ ]) [
    "storageFabric.seaweedfs.hotPool.enable is true but no host claims the 'seaweed-master' role."
  ]
  ++ lib.optionals (hotPoolEnabled && builtins.length masterHosts > 1) [
    "storageFabric.seaweedfs.hotPool currently supports exactly one declared 'seaweed-master' host; found: ${helpers.formatNames masterHosts}."
  ]
  ++ lib.optionals (hotPoolEnabled && seaweedVolumeHosts == [ ]) [
    "storageFabric.seaweedfs.hotPool.enable is true but no host claims the 'seaweed-volume' role."
  ]
  ++ lib.optionals (hotPoolEnabled && filerHosts == [ ]) [
    "storageFabric.seaweedfs.hotPool.enable is true but no host claims the 'seaweed-filer' role."
  ]
  ++ lib.optionals (replicationDigits == null) [
    "storageFabric.seaweedfs.hotPool.replication must be a three-digit SeaweedFS replication string such as '000' or '001'."
  ]
  ++
    lib.optionals
      (
        hotPoolEnabled
        && replicationCopies != null
        && builtins.length seaweedVolumeHosts < replicationCopies
      )
      [
        "storageFabric.seaweedfs.hotPool.replication '${replication}' requires at least ${toString replicationCopies} seaweed-volume hosts, but only ${toString (builtins.length seaweedVolumeHosts)} are declared: ${helpers.formatNames seaweedVolumeHosts}."
      ]
  ++
    lib.optionals
      (
        (lib.attrByPath [ "s3" "enable" ] false hotPool)
        && !(lib.any (h: hostHasRole h "seaweed-s3") (builtins.attrNames hosts))
      )
      [
        "storageFabric.seaweedfs.hotPool.s3.enable is true but no host claims the 'seaweed-s3' role."
      ]
  ++ lib.optionals ((lib.attrByPath [ "s3" "enable" ] false hotPool) && filerHosts == [ ]) [
    "storageFabric.seaweedfs.hotPool.s3.enable is true but no host claims the 'seaweed-filer' role for the S3 gateway to use."
  ]
  ++ lib.concatMap (
    hostName:
    let
      host = hosts.${hostName};
      isAnnexStorage = hostHasRole hostName "annex-storage";
      isSeaweedHost = builtins.elem hostName seaweedHosts;
      isArchiveNode = hostHasRole hostName "archive-node";
      isRadicleSeed = hostHasRole hostName "radicle-seed";
      onYgg = hostOnPrivateYgg hostName;
      archiveOrg = lib.attrByPath [ "org" "storage" "annex" "archive" ] { } host;
      nasOrg = archiveOrg.nas or { };
      tapeOrg = archiveOrg.tape or { };
      objectOrg = archiveOrg.object or { };
      removableOrg = archiveOrg.removableDisk or { };
      hasArchiveBackend =
        (nasOrg.enable or false)
        || (tapeOrg.enable or false)
        || (objectOrg.enable or false)
        || (removableOrg.enable or false);
    in
    lib.optionals (isAnnexStorage && !onYgg) [
      "Host '${hostName}' claims role 'annex-storage' but is not enrolled in ${privateNetwork}.  Annex storage hosts must be on the private overlay."
    ]
    ++ lib.optionals (isSeaweedHost && !onYgg) [
      "Host '${hostName}' claims a seaweedfs role but is not enrolled in ${privateNetwork}.  SeaweedFS hosts must be on the private overlay."
    ]
    ++ lib.optionals (isArchiveNode && !onYgg) [
      "Host '${hostName}' claims role 'archive-node' but is not enrolled in ${privateNetwork}.  Archive nodes must be reachable over the private overlay."
    ]
    ++
      lib.optionals
        (
          (isAnnexStorage || isSeaweedHost || isArchiveNode || isRadicleSeed)
          && onYgg
          && hostPrivateYggAddress hostName == null
        )
        [
          "Host '${hostName}' claims a storage-fabric service role but ${privateNetwork}.nodes.${hostName}.address is not set."
        ]
    ++ lib.optionals (isArchiveNode && !hasArchiveBackend) [
      "Host '${hostName}' claims role 'archive-node' but no archive backend is configured in org.storage.annex.archive.  Enable at least one of: nas, tape, object, removableDisk."
    ]
    ++ lib.optionals ((nasOrg.enable or false) && !(nasOrg ? path) && !(nasOrg ? mountPoint)) [
      "Host '${hostName}' enables archive NAS backend but does not set org.storage.annex.archive.nas.path or mountPoint."
    ]
    ++ lib.optionals ((tapeOrg.enable or false) && !hasTapeFacts host) [
      "Host '${hostName}' enables archive tape backend but is missing facts.storage.tape.devices.changer and at least one drive."
    ]
    ++ lib.optionals ((objectOrg.enable or false) && !(objectOrg ? endpoint)) [
      "Host '${hostName}' enables archive object backend but does not set org.storage.annex.archive.object.endpoint."
    ]
    ++
      lib.optionals
        ((objectOrg.enable or false) && (objectOrg ? endpoint) && isPublicContentRemote objectOrg.endpoint)
        [
          "Host '${hostName}' enables archive object endpoint '${objectOrg.endpoint}' which does not look private.  Object archive endpoints must stay on the private overlay unless public content transfers are explicitly allowed."
        ]
    ++ lib.optionals ((removableOrg.enable or false) && !(removableOrg ? path)) [
      "Host '${hostName}' enables removable-disk archive backend but does not set org.storage.annex.archive.removableDisk.path."
    ]
    ++ lib.optionals (isRadicleSeed && !onYgg) [
      "Host '${hostName}' claims role 'radicle-seed' but is not enrolled in ${privateNetwork}.  Radicle seed nodes must be on the private overlay."
    ]
    ++ lib.optionals (isRadicleSeed && onYgg && hostPrivateYggPublicKey hostName == null) [
      "Host '${hostName}' claims role 'radicle-seed' but ${privateNetwork}.nodes.${hostName}.publicKey is not set."
    ]
    # M11: per-host annex remote URL validation.
    ++ checkAnnexRemoteUrls hostName
  ) allFabricHosts
