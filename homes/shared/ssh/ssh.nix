{ lib, site, ... }:
let
  hostBootstrap = site.hostBootstrap or { };
  privateYggNodes = site.networks.privateYggdrasil.nodes or { };

  firstNonNull = fallback: values: lib.findFirst (value: value != null) fallback values;

  hostAliases =
    hostName:
    let
      bootstrap = hostBootstrap.${hostName} or { };
      targetHost = bootstrap.targetHost or null;
    in
    [ hostName ]
    ++ (privateYggNodes.${hostName}.aliases or [ ])
    ++ lib.optionals (targetHost != null) [ targetHost ];

  mkHostBlock =
    hostName:
    let
      bootstrap = hostBootstrap.${hostName} or { };
      yggNode = privateYggNodes.${hostName} or { };
      deploymentTransport = bootstrap.deploymentTransport or "bootstrap";
      identityFile = bootstrap.identityFile or null;
      preferredTransportTarget =
        if deploymentTransport == "privateYggdrasil" then
          firstNonNull null [
            (yggNode.deployHost or null)
            (yggNode.address or null)
          ]
        else
          null;
      hostname = firstNonNull hostName [
        preferredTransportTarget
        (bootstrap.targetHost or null)
        (yggNode.deployHost or null)
        (yggNode.endpointHost or null)
        hostName
      ];
    in
    {
      name = lib.concatStringsSep " " (hostAliases hostName);
      value = {
        inherit hostname;
        user = bootstrap.sshUser or "root";
      }
      // lib.optionalAttrs (identityFile != null) {
        identityFile = identityFile;
        identitiesOnly = true;
      };
    };
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
      ++ builtins.map mkHostBlock (builtins.attrNames hostBootstrap)
    );
  };
}
