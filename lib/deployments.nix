{ assembly, inputs, lib }:
let
  exportedHosts = inventory:
    lib.filterAttrs (_: host: host.exported or true) inventory.hosts;

  optionalAttr = name: value:
    lib.optionalAttrs (value != null) {
      "${name}" = value;
    };

  optionalAttrFrom = name: attrs:
    lib.optionalAttrs (builtins.hasAttr name attrs) {
      "${name}" = builtins.getAttr name attrs;
    };

  sanitizeTag = value:
    lib.replaceStrings [ "/" " " ":" "." ] [ "-" "-" "-" "-" ] (toString value);

  mkBaseTarget =
    {
      inventory,
      host,
      hostName,
    }:
    let
      deployment = lib.attrByPath [ "org" "deployment" ] { } host;
      bootstrap = lib.attrByPath [ "hostBootstrap" hostName ] { } inventory;
      privateYggNode = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" hostName ] { } inventory;
      deploymentTransport = deployment.transport or bootstrap.deploymentTransport or "bootstrap";
      identityFile = deployment.identityFile or bootstrap.identityFile or null;
      yggTargetHost = privateYggNode.deployHost or privateYggNode.address or null;
      preferredTransportTarget =
        # Use the logical host name so SSH resolves it through the operator's
        # Home Manager-managed SSH config (which already maps the name to the
        # Ygg address, identity file, and user).  Avoids embedding raw IPv6
        # addresses in deploy-rs / Colmena output.
        if deploymentTransport == "privateYggdrasil" && yggTargetHost != null then
          hostName
        else
          null;
      resolvedTargetHost = lib.findFirst (value: value != null) hostName [
        (deployment.targetHost or null)
        preferredTransportTarget
        (bootstrap.targetHost or null)
        (privateYggNode.deployHost or null)
        (privateYggNode.endpointHost or null)
        hostName
      ];
    in
    {
      inherit bootstrap deployment deploymentTransport privateYggNode;
      inherit identityFile;
      targetHost = resolvedTargetHost;
      targetPort = deployment.targetPort or 22;
      sshUser = deployment.sshUser or bootstrap.sshUser or "root";
      targetUser = deployment.targetUser or deployment.sshUser or "root";
      tags = lib.unique (
        [ hostName ]
        ++ (bootstrap.deploymentTags or [ ])
        ++ lib.optionals (bootstrap.operatorCapable or false) [ "operator-capable" ]
        ++ [ ("transport-" + sanitizeTag deploymentTransport) ]
        ++ (deployment.tags or [ ])
        ++ builtins.map (role: "role-" + sanitizeTag role) (host.roles or [ ])
        ++ builtins.map (dendrite: "dendrite-" + sanitizeTag dendrite) (host.dendrites or [ ])
        ++ builtins.map (fruit: "fruit-" + sanitizeTag fruit) (host.fruits or [ ])
      );
    };
in
rec {
  resolveDeploymentTarget = mkBaseTarget;

  mkColmenaNode =
    {
      genericSiteModule,
      inventory,
      registries,
      host,
      hostName,
    }:
    let
      base = mkBaseTarget {
        inherit inventory host hostName;
      };
      colmena = base.deployment.colmena or { };
      hostDefinition = assembly.mkHostDefinition {
        inherit genericSiteModule host hostName inventory registries;
      };
    in
    {
      imports = hostDefinition.modules;

      deployment =
        {
          targetHost = colmena.targetHost or base.targetHost;
          targetPort = colmena.targetPort or base.targetPort;
          targetUser = colmena.targetUser or base.sshUser;
          tags = lib.unique (base.tags ++ (colmena.tags or [ ]));
        }
        // optionalAttrFrom "allowLocalDeployment" colmena
        // optionalAttrFrom "buildOnTarget" colmena
        // optionalAttrFrom "replaceUnknownProfiles" colmena;
    };

  mkColmena =
    {
      genericSiteModule,
      inventory,
      registries,
    }:
    let
      exported = exportedHosts inventory;
    in
    {
      meta = {
        # meta.nixpkgs is mandatory in flake/hermetic mode and must be a
        # fully-evaluated set (not a lambda or path).  Use x86_64-linux as
        # the default and override per-node for hosts that differ.
        nixpkgs = import inputs.nixpkgs.outPath { system = "x86_64-linux"; };
        nodeNixpkgs = builtins.mapAttrs
          (hostName: host: import inputs.nixpkgs.outPath { system = host.system; })
          exported;
      };
    }
    // builtins.mapAttrs
      (hostName: host:
        mkColmenaNode {
          inherit genericSiteModule inventory registries host hostName;
        })
      exported;

  mkDeployRsNode =
    {
      inventory,
      nixosConfigurations,
      host,
      hostName,
    }:
    let
      base = mkBaseTarget {
        inherit inventory host hostName;
      };
      deployRs = base.deployment.deployRs or { };
      deployLib = inputs.deploy-rs.lib.${host.system} or (throw "deploy-rs does not support system '${host.system}' for host '${hostName}'.");
      sshPort = deployRs.targetPort or base.targetPort;
      sshOpts =
        (deployRs.sshOpts or [ ])
        ++ lib.optionals (base.identityFile != null) [
          "-i"
          base.identityFile
          "-o"
          "IdentitiesOnly=yes"
        ]
        ++ lib.optionals (sshPort != 22) [ "-p" (toString sshPort) ];
    in
    {
      hostname = deployRs.hostname or deployRs.targetHost or base.targetHost;
      profilesOrder = deployRs.profilesOrder or [ "system" ];
      sshUser = deployRs.sshUser or base.sshUser;

      profiles.system = {
        user = deployRs.user or deployRs.targetUser or base.targetUser;
        path = deployLib.activate.nixos nixosConfigurations.${hostName};
      }
      // optionalAttrFrom "profilePath" deployRs;
    }
    // optionalAttr "sshOpts" (if sshOpts == [ ] then null else sshOpts)
    // optionalAttrFrom "activationTimeout" deployRs
    // optionalAttrFrom "autoRollback" deployRs
    // optionalAttrFrom "confirmTimeout" deployRs
    // optionalAttrFrom "fastConnection" deployRs
    // optionalAttrFrom "interactiveSudo" deployRs
    // optionalAttrFrom "magicRollback" deployRs
    // optionalAttrFrom "remoteBuild" deployRs
    // optionalAttrFrom "sudo" deployRs
    // optionalAttrFrom "tempPath" deployRs;

  mkDeployRs =
    {
      inventory,
      nixosConfigurations,
    }:
    {
      nodes = builtins.mapAttrs
        (hostName: host:
          mkDeployRsNode {
            inherit inventory nixosConfigurations host hostName;
          })
        (exportedHosts inventory);
    };
}
