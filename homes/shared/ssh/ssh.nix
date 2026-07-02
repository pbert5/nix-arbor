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
  operatorIdentityFiles = lib.attrByPath [
    "users"
    currentUser
    "org"
    "ssh"
    "identityFiles"
  ] [ ] site;
  registryMaterializedPath = lib.attrByPath [
    "identityPolicy"
    "registry"
    "materializedPath"
  ] "/run/cluster-identity" site;

  firstNonNull = fallback: values: lib.findFirst (value: value != null) fallback values;

  withIdentity =
    identityFile:
    lib.optionalAttrs (identityFile != null) {
      IdentityFile = identityFile;
      IdentitiesOnly = true;
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
        HostName = hostname;
        User = user;
      }
      // withIdentity identityFile
      // lib.optionalAttrs (hostKeyAlias != null) {
        HostKeyAlias = hostKeyAlias;
      }
      // lib.optionalAttrs (remoteCommand != null) {
        RemoteCommand = remoteCommand;
      }
      // lib.optionalAttrs (requestTTY != null) {
        RequestTTY = requestTTY;
      };
    };

  mkDeployHostBlock =
    hostName:
    let
      bootstrap = hostBootstrap.${hostName} or { };
      yggNode = privateYggNodes.${hostName} or { };
      deploymentTransport = bootstrap.deploymentTransport or "bootstrap";
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
      inherit hostname;
      user = bootstrap.sshUser or "root";
    };

  mkYggHostBlock =
    hostName:
    let
      bootstrap = hostBootstrap.${hostName} or { };
      yggNode = privateYggNodes.${hostName} or { };
      yggTarget = firstNonNull null [
        (yggNode.deployHost or null)
        (yggNode.address or null)
      ];
      aliases = lib.unique ([ "${hostName}-ygg" ] ++ (yggNode.aliases or [ ]));
    in
    lib.optional (yggTarget != null) (mkHostBlock {
      name = lib.concatStringsSep " " aliases;
      hostname = yggTarget;
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
      hostUsers = hosts.${hostName}.users or [ ];
      userHostname = firstNonNull hostName [
        (yggNode.deployHost or null)
        (yggNode.address or null)
        (bootstrap.targetHost or null)
        (yggNode.endpointHost or null)
        hostName
      ];
    in
    builtins.map (
      userName:
      mkHostBlock {
        name = "${hostName}-${userName}";
        hostname = userHostname;
        user = userName;
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
  operatorHostPatterns = lib.concatStringsSep "," (
    lib.concatMap (
      hostName:
      [
        hostName
        "${hostName}-ygg"
        "${hostName}-bootstrap"
        "${hostName}-${currentUser}"
      ]
    ) (builtins.attrNames hostBootstrap)
  );
  operatorIdentityMatchConfig = lib.concatMapStringsSep "\n" (identityFile: ''
    Match originalhost ${operatorHostPatterns} exec "test -r ${identityFile}"
      IdentityFile ${identityFile}
  '') operatorIdentityFiles;
in
{
  programs.ssh = {
    enable = true;
    enableDefaultConfig = false;
    extraConfig = operatorIdentityMatchConfig;
    includes = [ "${registryMaterializedPath}/ssh_config" ];
    settings = builtins.listToAttrs (
      [
        {
          name = "*";
          value = {
            AddKeysToAgent = "no";
            ControlMaster = "no";
            ControlPersist = "no";
            ServerAliveCountMax = 3;
            ServerAliveInterval = 0;
            UserKnownHostsFile = "~/.ssh/known_hosts";
            # Remote hosts don't ship a terminfo entry for $TERM=xterm-kitty,
            # which makes zsh's line editor garble input (TERM falls back to dumb).
            SetEnv = {
              TERM = "xterm-256color";
            };
          };
        }
      ]
      ++ hostBlocks
    );
  };
}
