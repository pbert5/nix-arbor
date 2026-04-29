{
  hostInventory,
  hostName,
  lib,
  site,
  ...
}:
let
  cfg = lib.attrByPath [ "org" "nix" "distributedBuilds" ] { } hostInventory;
  builderNames = cfg.builders or [ ];
  bootstrap = site.hostBootstrap or { };
  privateYggNodes = lib.attrByPath [ "networks" "privateYggdrasil" "nodes" ] { } site;

  # For Ygg-transport hosts we keep the logical name (e.g. "r640-0") as the
  # SSH hostname and let programs.ssh.extraConfig (generated below) map it to
  # the raw Ygg address.  Raw IPv6 literals in nix.buildMachines.hostName
  # are passed to ssh without brackets and break the connection.
  resolveHostName = builderName:
    let
      builderBootstrap = bootstrap.${builderName} or { };
      builderYgg = privateYggNodes.${builderName} or { };
      transport = builderBootstrap.deploymentTransport or "bootstrap";
      # Keep logical name for Ygg hosts so SSH config can supply HostName +
      # IdentityFile via the generated block (see programs.ssh.extraConfig).
      yggTarget =
        if transport == "privateYggdrasil" then builderName else null;
    in
    lib.findFirst (value: value != null) builderName [
      yggTarget
      (builderBootstrap.targetHost or null)
      (builderYgg.deployHost or null)
      (builderYgg.endpointHost or null)
      builderName
    ];

  # Generate a system-wide SSH client config block for each builder that
  # connects over the private Yggdrasil overlay, so that root (as the
  # nix-daemon user) can resolve the logical name and authenticate.
  mkBuilderSshBlock = builderName:
    let
      builderBootstrap = bootstrap.${builderName} or { };
      builderYgg = privateYggNodes.${builderName} or { };
      transport = builderBootstrap.deploymentTransport or "bootstrap";
      yggAddr = builderYgg.deployHost or builderYgg.address or null;
      builderHost = site.hosts.${builderName} or { };
      builderCfg = lib.attrByPath [ "org" "nix" "buildMachine" ] { } builderHost;
      builderOverride = lib.attrByPath [ "builderOverrides" builderName ] { } cfg;
      sshKey = builderOverride.sshKey or cfg.sshKey or builderCfg.sshKey or null;
    in
    lib.optionalString (transport == "privateYggdrasil" && yggAddr != null) ''
      Host ${builderName}
        HostName ${yggAddr}
        User root
        ${lib.optionalString (sshKey != null) "IdentityFile ${sshKey}"}
        IdentitiesOnly ${if sshKey != null then "yes" else "no"}
        StrictHostKeyChecking accept-new
    '';

  builderSshConfig = lib.concatStrings (
    builtins.map mkBuilderSshBlock (
      builtins.filter (n: n != hostName) builderNames
    )
  );

  mkBuildMachine = builderName:
    let
      builderHost =
        site.hosts.${builderName}
          or (throw "Host '${hostName}' selects distributed build machine '${builderName}', but no such inventory host exists.");
      builderCfg = lib.attrByPath [ "org" "nix" "buildMachine" ] { } builderHost;
      builderOverride = lib.attrByPath [ "builderOverrides" builderName ] { } cfg;
      sshKey = builderOverride.sshKey or cfg.sshKey or null;
      publicHostKey = builderOverride.publicHostKey or builderCfg.publicHostKey or null;
    in
    {
      hostName = builderOverride.hostName or builderCfg.hostName or resolveHostName builderName;
      protocol = builderOverride.protocol or builderCfg.protocol or cfg.protocol or "ssh-ng";
      sshUser = builderOverride.sshUser or builderCfg.sshUser or cfg.sshUser or "root";
      systems = builderOverride.systems or builderCfg.systems or [ builderHost.system ];
      maxJobs = builderOverride.maxJobs or builderCfg.maxJobs or 1;
      speedFactor = builderOverride.speedFactor or builderCfg.speedFactor or 1;
      supportedFeatures =
        builderOverride.supportedFeatures
          or builderCfg.supportedFeatures
          or [
            "nixos-test"
            "benchmark"
            "big-parallel"
            "kvm"
          ];
      mandatoryFeatures = builderOverride.mandatoryFeatures or builderCfg.mandatoryFeatures or [ ];
    }
    // lib.optionalAttrs (sshKey != null) { inherit sshKey; }
    // lib.optionalAttrs (publicHostKey != null) { inherit publicHostKey; };

  buildMachines = builtins.map mkBuildMachine (builtins.filter (builderName: builderName != hostName) builderNames);
in
{
  nix.distributedBuilds = cfg.enable or (buildMachines != [ ]);
  nix.buildMachines = buildMachines;
  nix.settings.builders-use-substitutes = cfg.buildersUseSubstitutes or true;

  # Provide a system-wide SSH client config so the nix-daemon (running as
  # root) can resolve logical builder hostnames to their Yggdrasil addresses
  # and authenticate with the configured SSH key.
  programs.ssh.extraConfig = lib.mkIf (builderSshConfig != "") (
    lib.mkAfter builderSshConfig
  );
}
