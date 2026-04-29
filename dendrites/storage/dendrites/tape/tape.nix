{
  lib,
  pkgs,
  site,
  hostInventory,
  ...
}:
let
  endpoints = import ../../../../lib/endpoints.nix { inherit lib; };
  yamlFormat = pkgs.formats.yaml { };
  tapeLibraryPackages = pkgs.callPackage ./_packages/tape-library-packages.nix {
    driveDevices = driveDevices;
    inherit lib;
    ports = site.ports or { };
  };
  ltfsOpenFromFruit = pkgs.callPackage ../../../../fruits/fossilsafe/nix/ltfs-open.nix { };
  yatmEndpoint = endpoints.normalizeEndpoint 8081 (site.ports.tapeLibraryYatm or { });
  yatmDebugEndpoint = endpoints.normalizeEndpoint 8082 (site.ports.tapeLibraryYatmDebug or { });
  fossilsafeEndpoint = endpoints.normalizeEndpoint 5001 (site.ports.tapeLibraryFossilsafe or { });
  tapeFacts = lib.attrByPath [ "facts" "storage" "tape" "devices" ] { } hostInventory;
  driveDevices =
    if tapeFacts ? drives then
      tapeFacts.drives
    else if tapeFacts ? drive then
      [ tapeFacts.drive ]
    else
      [ ];
  driveDevice =
    if tapeFacts ? drive then
      tapeFacts.drive
    else if driveDevices == [ ] then
      null
    else
      builtins.head driveDevices;
  changerDevice = tapeFacts.changer or null;
  tapeOrg = lib.attrByPath [ "org" "storage" "tape" ] { } hostInventory;
  fossilsafeOrg = tapeOrg.fossilsafe or { };
  tapelibOrg = tapeOrg.tapelib or { };
  yatmOrg = tapeOrg.yatm or { };
  selectedLtfsManager = tapeOrg.manager or null;
  fossilsafePackage =
    if selectedLtfsManager == "fossilsafe" then
      pkgs.callPackage ../../../../fruits/fossilsafe/nix/fossilsafe-package.nix {
        ltfsOpen = ltfsOpenFromFruit;
        sourceRoot = ../../../../fruits/fossilsafe/FOSSILSAFE;
      }
    else
      null;
  tapelibPackage =
    if selectedLtfsManager == "tapelib" then
      pkgs.callPackage ../../../../fruits/tapelib/nix/tapelib-package.nix {
        sourceRoot = ../../../../fruits/tapelib;
      }
    else
      null;
  inherit (tapeLibraryPackages)
    changerDefault
    ltfsDefault
    ltfsOpen
    mt1WithDefaults
    mt2WithDefaults
    mtWithDefaults
    mtxWithDefaults
    stfs
    tapeDefault
    yatm
    ;
  selectedLtfsManagerPackage =
    if selectedLtfsManager == null then
      null
    else
      {
        fossilsafe = fossilsafePackage;
        tapelib = tapelibPackage;
        yatm = yatm;
      }
      .${selectedLtfsManager};
  fossilsafeDeviceSettings =
    lib.optionalAttrs (changerDevice != null || driveDevice != null || driveDevices != [ ])
      {
        tape =
          (lib.optionalAttrs (changerDevice != null) { changer_device = changerDevice; })
          // (lib.optionalAttrs (driveDevice != null) { drive_device = driveDevice; })
          // (lib.optionalAttrs (driveDevices != [ ]) { drive_devices = driveDevices; });
      };
  fossilsafeSettings = lib.recursiveUpdate (lib.attrByPath [
    "settings"
  ] { } fossilsafeOrg) fossilsafeDeviceSettings;
  tapelibStateDir = lib.attrByPath [ "stateDir" ] "/var/lib/tapelib" tapelibOrg;
  tapelibDriveDefs = builtins.genList (
    index:
    let
      stDevice = builtins.elemAt driveDevices index;
      configuredDrives = lib.attrByPath [ "library" "drives" ] [ ] tapelibOrg;
      configuredDrive =
        if index < builtins.length configuredDrives then builtins.elemAt configuredDrives index else { };
    in
    {
      mountPath = lib.attrByPath [
        "mountPath"
      ] "${tapelibStateDir}/mounts/drive${toString index}" configuredDrive;
      name = lib.attrByPath [ "name" ] "drive${toString index}" configuredDrive;
      sgDevice = lib.attrByPath [ "sgDevice" ] null configuredDrive;
      inherit stDevice;
    }
  ) (builtins.length driveDevices);
  tapelibConfig = {
    cache = lib.attrByPath [ "cache" ] {
      maxBytes = "900G";
      path = "/run/media/ash/cache/tapelib";
      reservedFreeBytes = "50G";
    } tapelibOrg;
    database = lib.attrByPath [ "database" ] {
      path = "${tapelibStateDir}/catalog.sqlite";
    } tapelibOrg;
    fuse = lib.attrByPath [ "fuse" ] {
      group = "users";
      mountPoint = "/mnt/tapelib";
      user = "ash";
    } tapelibOrg;
    games = lib.attrByPath [ "games" ] {
      namespacePrefix = "/games";
      selectedTapes = [ ];
      sourceRoots = [
        "/home/example/games/incoming"
        "/home/example/games/_source-archives"
      ];
      tapeCapacityBytes = 1400000000000;
    } tapelibOrg;
    library = {
      allowedGenerations = lib.attrByPath [ "library" "allowedGenerations" ] [ "L5" ] tapelibOrg;
      changerDevice = lib.attrByPath [ "library" "changerDevice" ] changerDevice tapelibOrg;
      drives = tapelibDriveDefs;
    };
    openFirewall = lib.attrByPath [ "openFirewall" ] false tapelibOrg;
    package = tapelibPackage;
    stateDir = tapelibStateDir;
    webui = lib.attrByPath [ "webui" ] {
      enable = true;
      host = "127.0.0.1";
      port = 5001;
    } tapelibOrg;
  };
  yatmStateDir = lib.attrByPath [ "stateDir" ] "/var/lib/yatm" yatmOrg;
  yatmSettings = lib.recursiveUpdate {
    database = {
      dialect = "sqlite";
      dsn = "${yatmStateDir}/tapes.db";
    };
    debug_listen = "${yatmDebugEndpoint.bind}:${toString yatmDebugEndpoint.port}";
    domain = yatmEndpoint.url;
    listen = "${yatmEndpoint.bind}:${toString yatmEndpoint.port}";
    paths = {
      source = "/";
      target = "/";
      work = "${yatmStateDir}/work";
    };
    scripts = {
      encrypt = "${yatm}/share/yatm/scripts/encrypt";
      mkfs = "${yatm}/share/yatm/scripts/mkfs";
      mount = "${yatm}/share/yatm/scripts/mount";
      read_info = "${yatm}/share/yatm/scripts/readinfo";
      umount = "${yatm}/share/yatm/scripts/umount";
    };
    tape_devices = driveDevices;
  } (lib.attrByPath [ "settings" ] { } yatmOrg);
  yatmConfigFile = yamlFormat.generate "yatm-config.yaml" yatmSettings;
in
{
  _module.args.storageTape = {
    selectedLtfsManager = selectedLtfsManager;
    fossilsafe = {
      bootstrap = lib.attrByPath [ "bootstrap" ] { } fossilsafeOrg;
      endpoint = fossilsafeEndpoint;
      openFirewall = lib.attrByPath [ "openFirewall" ] false fossilsafeOrg;
      package = fossilsafePackage;
      requireApiKey = lib.attrByPath [ "requireApiKey" ] false fossilsafeOrg;
      settings = fossilsafeSettings;
      skipHardwareInit = lib.attrByPath [ "skipHardwareInit" ] false fossilsafeOrg;
      stateDir = lib.attrByPath [ "stateDir" ] "/var/lib/fossilsafe" fossilsafeOrg;
    };
    tapelib = tapelibConfig;
  };

  boot.kernelModules = [
    "sg"
    "st"
  ];

  environment.etc."yatm/config.yaml".source = yatmConfigFile;

  environment.sessionVariables = lib.mkIf (selectedLtfsManager == "yatm") {
    YATM_CAPTURED_INDICES_DIR = "${yatmStateDir}/captured_indices";
    YATM_CONFIG = "/etc/yatm/config.yaml";
    YATM_STATE_DIR = yatmStateDir;
  };

  environment.systemPackages =
    (with pkgs; [
      bacula
      changerDefault
      gnutar
      lsscsi
      ltfsDefault
      ltfsOpen
      mt1WithDefaults
      mt2WithDefaults
      sg3_utils
      stfs
      tapeDefault
      mtWithDefaults
      mtxWithDefaults
    ])
    ++ lib.optionals (selectedLtfsManagerPackage != null) [ selectedLtfsManagerPackage ];
}
