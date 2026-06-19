{
  config,
  lib,
  site,
  ...
}:
let
  hostBootstrap = site.hostBootstrap or { };
  hosts = site.hosts or { };
  privateYggNodes = site.networks.privateYggdrasil.nodes or { };
  currentUser = config.home.username or null;

  firstNonNull = fallback: values: lib.findFirst (value: value != null) fallback values;

  withIdentity =
    identityFile:
    lib.optionalAttrs (identityFile != null) {
      inherit identityFile;
      identitiesOnly = true;
    };

  mkHostBlock =
    {
      name,
      hostname,
      user,
      identityFile ? null,
      hostKeyAlias ? null,
      remoteCommand ? null,
      requestTTY ? null,
    }:
    {
      inherit name;
      value = {
        inherit hostname user;
      }
      // withIdentity identityFile
      // {
        extraOptions =
          lib.optionalAttrs (hostKeyAlias != null) {
            HostKeyAlias = hostKeyAlias;
          }
          // lib.optionalAttrs (remoteCommand != null) {
            RemoteCommand = remoteCommand;
          }
          // lib.optionalAttrs (requestTTY != null) {
            RequestTTY = requestTTY;
          };
      };
    };

  mkDeployHostBlock =
    hostName:
    let
      bootstrap = hostBootstrap.${hostName} or { };
      yggNode = privateYggNodes.${hostName} or { };
      deploymentTransport = bootstrap.deploymentTransport or "bootstrap";
      identityFile = bootstrap.identityFile or null;
      yggTarget = firstNonNull null [
        (yggNode.deployHost or null)
        (yggNode.address or null)
      ];
      hostname =
        if deploymentTransport == "privateYggdrasil" then
          firstNonNull hostName [
            yggTarget
            (bootstrap.targetHost or null)
            (yggNode.endpointHost or null)
            hostName
          ]
        else
          firstNonNull hostName [
            (bootstrap.targetHost or null)
            (yggNode.endpointHost or null)
            hostName
          ];
    in
    mkHostBlock {
      name = hostName;
      inherit hostname identityFile;
      user = bootstrap.sshUser or "root";
    };

  mkYggHostBlock =
    hostName:
    let
      bootstrap = hostBootstrap.${hostName} or { };
      yggNode = privateYggNodes.${hostName} or { };
      identityFile = bootstrap.identityFile or null;
      yggTarget = firstNonNull null [
        (yggNode.deployHost or null)
        (yggNode.address or null)
      ];
      aliases = lib.unique ([ "${hostName}-ygg" ] ++ (yggNode.aliases or [ ]));
    in
    lib.optional (yggTarget != null) (mkHostBlock {
      name = lib.concatStringsSep " " aliases;
      hostname = yggTarget;
      inherit identityFile;
      hostKeyAlias = hostName;
      user = bootstrap.sshUser or "root";
    });

  mkBootstrapHostBlock =
    hostName:
    let
      bootstrap = hostBootstrap.${hostName} or { };
      identityFile = bootstrap.identityFile or null;
      targetHost = bootstrap.targetHost or null;
    in
    lib.optional (targetHost != null) (mkHostBlock {
      name = "${hostName}-bootstrap";
      hostname = targetHost;
      inherit identityFile;
      hostKeyAlias = hostName;
      user = bootstrap.sshUser or "root";
    });

  mkUserHostBlocks =
    hostName:
    let
      bootstrap = hostBootstrap.${hostName} or { };
      yggNode = privateYggNodes.${hostName} or { };
      identityFile = bootstrap.identityFile or null;
      hostUsers = hosts.${hostName}.users or [ ];
      userHostname = firstNonNull hostName [
        (yggNode.deployHost or null)
        (yggNode.address or null)
        (bootstrap.targetHost or null)
        (yggNode.endpointHost or null)
        hostName
      ];
      identityFileForUser = userName: if userName == currentUser then identityFile else null;
    in
    builtins.map (
      userName:
      mkHostBlock {
        name = "${hostName}-${userName}";
        hostname = userHostname;
        user = userName;
        identityFile = identityFileForUser userName;
        hostKeyAlias = hostName;
        remoteCommand = "sh";
        requestTTY = "no";
      }
    ) hostUsers;

  mkHostBlocks =
    hostName:
    [
      (mkDeployHostBlock hostName)
    ]
    ++ mkYggHostBlock hostName
    ++ mkBootstrapHostBlock hostName
    ++ mkUserHostBlocks hostName;

  hostBlocks = lib.concatMap mkHostBlocks (builtins.attrNames hostBootstrap);
in
{
  programs.ssh = {
    enable = true;
    enableDefaultConfig = false;
    matchBlocks = builtins.listToAttrs (
      [
        {
          name = "*";
          value = {
            addKeysToAgent = "no";
            controlMaster = "no";
            controlPersist = "no";
            serverAliveCountMax = 3;
            serverAliveInterval = 0;
            userKnownHostsFile = "~/.ssh/known_hosts";
          };
        }
      ]
      ++ hostBlocks
    );
  };
}
