{ lib }:
let
  nodeSelection = import ./node-selection.nix { inherit lib; };
  deploymentPlan = import ./deployment-plan.nix { inherit lib nodeSelection; };
  colmena = import ./colmena.nix { inherit lib; };
  sourceMergeLib = import ./source-merge.nix { inherit lib; };
  sourceMerge = sourceMergeLib.sourceMerge;

  publicMachineFields = [
    "identity"
    "system"
    "platform"
    "profiles"
    "hostname"
    "cluster"
    "enabled"
    "provenance"
    "precedence"
    "hardware"
    "intent"
    "endpoints"
    "services"
    "compatibility"
    "metadata"
    "target"
    "targetHost"
    "targetPort"
    "targetUser"
    "tags"
  ];

  unsafeKey =
    name:
    let
      normalized = lib.toLower (builtins.replaceStrings [ "-" "_" ] [ "" "" ] name);
    in
    lib.elem normalized [
      "secret"
      "password"
      "passphrase"
      "token"
      "credential"
      "privatekey"
      "signingkey"
      "apikey"
      "apitoken"
      "accesstoken"
      "seed"
    ];

  unsafeString =
    value:
    builtins.isString value
    && (
      lib.hasPrefix "/nix/store/" value
      || lib.hasPrefix "/run/secrets/" value
      || lib.hasPrefix "/run/credentials/" value
      || lib.hasPrefix "/var/run/secrets/" value
      || lib.hasPrefix "-----BEGIN" value
    );

  validatePublicValue =
    context: value:
    if builtins.isFunction value then
      throw "Arbor Manager: ${context} contains an executable function."
    else if builtins.typeOf value == "path" then
      let
        pathValue = toString value;
      in
      if lib.hasPrefix "/nix/store/" pathValue then
        throw "Arbor Manager: ${context} contains an unsafe store path."
      else
        true
    else if unsafeString value then
      throw "Arbor Manager: ${context} contains an unsafe secret or runtime value."
    else if builtins.isList value then
      builtins.all (item: validatePublicValue context item) value
    else if builtins.isAttrs value then
      if (value.type or null) == "derivation" || builtins.hasAttr "__functor" value then
        throw "Arbor Manager: ${context} contains an executable derivation or functor."
      else
        builtins.all (
          name:
          if unsafeKey name then
            throw "Arbor Manager: ${context} contains secret-like key '${name}'."
          else
            validatePublicValue "${context}.${name}" value.${name}
        ) (builtins.attrNames value)
    else
      true;

  sanitizeMachineRecord =
    name: raw:
    let
      _safe = validatePublicValue "machine '${name}'" raw;
    in
    assert _safe;
    builtins.intersectAttrs (lib.genAttrs publicMachineFields (_: true)) raw;

  machineTypes = {
    system = lib.types.enum [
      "x86_64-linux"
      "aarch64-linux"
    ];
    profiles = lib.types.listOf lib.types.str;
  };

  validateMachine =
    name: raw:
    let
      sanitized = sanitizeMachineRecord name raw;
      required =
        field:
        if builtins.hasAttr field sanitized then
          builtins.getAttr field sanitized
        else
          throw "Arbor Manager: machine '${name}' is missing required field '${field}'.";
      system = required "system";
      _system =
        if
          builtins.elem system [
            "x86_64-linux"
            "aarch64-linux"
          ]
        then
          true
        else
          throw "Arbor Manager: machine '${name}' has unsupported system '${system}'.";
      hostname = sanitized.hostname or name;
      profiles = sanitized.profiles or [ ];
      cluster = sanitized.cluster or { };
      provenance = sanitized.provenance or { kind = "inline"; };
      precedence = sanitized.precedence or 0;
    in
    assert lib.assertMsg (
      builtins.match "[a-zA-Z0-9][a-zA-Z0-9-]*" name != null
    ) "Arbor Manager: machine directory name '${name}' is not a valid hostname-like identifier.";
    assert lib.assertMsg (
      builtins.isList profiles && builtins.all builtins.isString profiles
    ) "Arbor Manager: machine '${name}' profiles must be a list of strings.";
    assert lib.assertMsg (
      builtins.match "[a-zA-Z0-9][a-zA-Z0-9-]*" hostname != null
    ) "Arbor Manager: machine '${name}' has an invalid hostname '${hostname}'.";
    assert _system;
    {
      inherit
        name
        hostname
        profiles
        system
        cluster
        provenance
        precedence
        ;
      enabled = sanitized.enabled or true;
    }
    // lib.optionalAttrs (builtins.hasAttr "target" sanitized) { inherit (sanitized) target; }
    // lib.optionalAttrs (builtins.hasAttr "targetHost" sanitized) { inherit (sanitized) targetHost; }
    // lib.optionalAttrs (builtins.hasAttr "targetPort" sanitized) { inherit (sanitized) targetPort; }
    // lib.optionalAttrs (builtins.hasAttr "targetUser" sanitized) { inherit (sanitized) targetUser; }
    // lib.optionalAttrs (builtins.hasAttr "tags" sanitized) { inherit (sanitized) tags; };
  # The intersection above is intentional: source records are data only.
  # Local modules are carried by the separate `modules` field on a source.

  optionalModule = path: if builtins.pathExists path then [ path ] else [ ];

  discover =
    machinesPath:
    let
      entries = builtins.readDir machinesPath;
      names = builtins.sort builtins.lessThan (
        builtins.filter (name: entries.${name} == "directory") (builtins.attrNames entries)
      );
    in
    builtins.listToAttrs (
      map (name: {
        inherit name;
        value = "${toString machinesPath}/${name}";
      }) names
    );

  localSource =
    machinesPath:
    builtins.attrValues (
      builtins.mapAttrs (name: directory: {
        inherit name directory;
        record = import "${directory}/default.nix";
        modules =
          optionalModule "${directory}/hardware-configuration.nix"
          ++ optionalModule "${directory}/configuration.nix";
        provenance = {
          kind = "local";
        };
        precedence = 0;
      }) (discover machinesPath)
    );

  registrySnapshot =
    {
      digest,
      machines,
    }:
    assert lib.assertMsg (
      builtins.isString digest && digest != ""
    ) "Arbor Manager: registry snapshots require a non-empty digest.";
    lib.mapAttrsToList (name: record: {
      inherit name;
      record = sanitizeMachineRecord name record;
      modules = [ ];
      provenance = {
        kind = "registry-snapshot";
        inherit digest;
      };
      precedence = 0;
    }) machines;

  mkMachine =
    {
      inputs,
      profiles,
      name,
      record,
      modules ? [ ],
      provenance ? {
        kind = "inline";
      },
      precedence ? 0,
      extraModules,
    }:
    let
      machine = validateMachine name (
        record
        // {
          provenance = record.provenance or provenance;
          precedence = record.precedence or precedence;
        }
      );
      profileNames = machine.profiles;
      missingProfiles = builtins.filter (profile: !(builtins.hasAttr profile profiles)) profileNames;
      profileModules = lib.concatMap (profile: profiles.${profile}) profileNames;
      _profiles =
        if missingProfiles == [ ] then
          true
        else
          throw "Arbor Manager: machine '${name}' references unknown profile(s): ${lib.concatStringsSep ", " missingProfiles}.";
      managerModule = { lib, ... }: {
        options.arbor.machine = lib.mkOption {
          type = lib.types.raw;
          readOnly = true;
          description = "Normalized Arbor Manager machine record.";
        };
        config = {
          assertions = [
            {
              assertion = machine.enabled;
              message = "Arbor Manager: disabled machine '${name}' cannot be built.";
            }
          ];
          networking.hostName = machine.hostname;
          nixpkgs.hostPlatform = lib.mkDefault machine.system;
          arbor.machine = machine;
        };
      };
    in
    assert _profiles;
    {
      inherit machine;
      modules = [ managerModule ] ++ profileModules ++ modules ++ extraModules;
    };
in
{
  inherit
    machineTypes
    sanitizeMachineRecord
    validateMachine
    discover
    localSource
    registrySnapshot
    sourceMerge
    ;

  inherit (nodeSelection) graph selectors select;
  inherit (deploymentPlan) plan;
  inherit (colmena) rawHive;

  mkMachines =
    {
      inputs,
      sources ? null,
      machinesPath ? null,
      profiles ? { },
      extraModules ? [ ],
      deploymentPlanOverride ? null,
    }:
    let
      sourceEntries =
        if sources != null then
          sources
        else if machinesPath != null then
          localSource machinesPath
        else
          throw "Arbor Manager: mkMachines requires 'sources' or 'machinesPath'.";
      machines = builtins.listToAttrs (
        map (
          source:
          let
            name = source.name;
          in
          {
            inherit name;
            value = mkMachine {
              inherit
                inputs
                profiles
                name
                extraModules
                ;
              record = source.record;
              modules = source.modules or [ ];
              provenance = source.provenance or { kind = "inline"; };
              precedence = source.precedence or 0;
            };
          }
        ) sourceEntries
      );
      configurations = builtins.mapAttrs (
        _name: machine:
        inputs.nixpkgs.lib.nixosSystem {
          inherit (machine.machine) system;
          specialArgs = {
            inherit inputs;
            machine = machine.machine;
          };
          modules = machine.modules;
        }
      ) machines;
    in
    let
      colmenaOutput =
        if !(builtins.hasAttr "colmena" inputs) then
          { }
        else
          let
            selectedPlan =
              if deploymentPlanOverride != null then
                deploymentPlanOverride
              else
                deploymentPlan.plan {
                  nodes = builtins.mapAttrs (_: machine: machine.machine) machines;
                  roots = [ ];
                };
            raw = colmena.rawHive {
              inherit machines;
              plan = selectedPlan;
              snapshotDigest = selectedPlan.snapshotDigest;
            };
          in
          {
            colmenaRawHive = raw;
            colmenaSelection = selectedPlan.names;
            colmenaHive = inputs.colmena.lib.makeHive raw;
          };
    in
    {
      inherit configurations machines;
      machineNames = builtins.attrNames machines;
    }
    // colmenaOutput;
}
