{
  lib,
  pkgs,
  inputs,
  site,
  hostInventory,
  hostName,
  ...
}:
let
  endpoints = import ../../../../lib/endpoints.nix { inherit lib; };
  jsonFormat = pkgs.formats.json { };
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
  changerDevice = if (tapeFacts.changer or null) == "manual" then null else tapeFacts.changer or null;
  tapeOrg = lib.attrByPath [ "org" "storage" "tape" ] { } hostInventory;
  backupPlans = lib.attrByPath [ "storage" "backupPlans" ] { } site;
  backupperPlans = lib.filterAttrs (
    _planName: plan:
    (plan.enable or true) && (plan.host or null) == hostName && (plan.tool or "") == "backupper"
  ) backupPlans;
  gameBackuperPlans = lib.filterAttrs (
    _planName: plan:
    (plan.enable or true) && (plan.host or null) == hostName && (plan.tool or "") == "game-backuper"
  ) backupPlans;
  fossilsafeOrg = tapeOrg.fossilsafe or { };
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
  inherit (tapeLibraryPackages)
    backupper
    backupperRunner
    changerDefault
    ltfsDefault
    ltfsDefault2
    ltfsOpen
    mt1WithDefaults
    mt2WithDefaults
    mtWithDefaults
    mtxWithDefaults
    stfs
    tapelibPackage
    tapeDefault
    tapeDefault2
    yatm
    ;
  selectedLtfsManagerPackage =
    if selectedLtfsManager == null then
      null
    else
      {
        fossilsafe = fossilsafePackage;
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
  yatmStateDir = lib.attrByPath [ "stateDir" ] "/var/lib/yatm" yatmOrg;
  yatmSettings =
    if selectedLtfsManager == "yatm" then
      lib.recursiveUpdate {
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
      } (lib.attrByPath [ "settings" ] { } yatmOrg)
    else
      null;
  yatmConfigFile =
    if yatmSettings == null then
      null
    else
      yamlFormat.generate "yatm-config.yaml" yatmSettings;
  gameBackuperPlanConfig =
    plan:
    builtins.removeAttrs plan [
      "description"
      "enable"
      "host"
      "source_flake"
      "tool"
    ];
  gameBackuperPlanFiles = lib.mapAttrs (
    planName: plan: yamlFormat.generate "game-backuper-${planName}.yaml" (gameBackuperPlanConfig plan)
  ) gameBackuperPlans;
  backupperPlanConfig =
    planName: plan:
    let
      stateDir = plan.state_dir or "/var/lib/backupper/${planName}";
      driveConfigs = lib.imap0 (
        index: stDevice:
        {
          name = "drive${toString index}";
          inherit stDevice;
          mountPath = "${stateDir}/mount/drive${toString index}";
          sgDevice = null;
        }
      ) driveDevices;
    in
    {
      planName = planName;
      stateDir = stateDir;
      database = {
        path = "${stateDir}/catalog.sqlite";
        backupDir = "${stateDir}/backups";
      };
      cache = {
        path = "${stateDir}/unused-cache";
        maxBytes = "1";
        reservedFreeBytes = "0";
      };
      scheduler = {
        automaticRetrieve = false;
        pollSeconds = 5;
        unloadAfterRetrieve = true;
      };
      fuse = {
        enable = false;
        group = "root";
        homeLink = null;
        metadataCacheSeconds = 1.0;
        mountPoint = "${stateDir}/fuse";
        user = "root";
      };
      webui = {
        enable = false;
        host = "127.0.0.1";
        port = 0;
      };
      library = {
        allowedGenerations = plan.allowed_generations or [ "L5" ];
        changerDevice = changerDevice;
        drives = driveConfigs;
      };
      games = {
        namespacePrefix = plan.namespace_prefix or "/games";
        selectedTapes = plan.selected_tapes or [ ];
        sourceRoots = plan.source_roots or [ ];
        tapeCapacityBytes = plan.tape_capacity_bytes or 1200000000000;
      };
      archive = {
        autoInitializeLtfs = plan.auto_initialize_ltfs or true;
        catalogLoadedTapeBeforeWrite = plan.catalog_loaded_tape_before_write or true;
        directSourceWrite = plan.direct_source_write or true;
        smallFileBundleMaxBytes = plan.small_file_bundle_max_bytes or "0";
        smallFileBundleTargetBytes = plan.small_file_bundle_target_bytes or "256M";
      };
      coverage = {
        archiveRoots = plan.coverage_archive_roots or (plan.source_roots or [ ]);
        looseRoots = plan.loose_roots or [ ];
        zipExtensions = plan.coverage_zip_extensions or [ ".zip" ];
        failOnMissing = plan.coverage_fail_on_missing or false;
        maxMissingBytes = plan.coverage_max_missing_bytes or null;
      };
      backupper = {
        description = plan.description or "Declarative LTFS backupper plan.";
      };
    };
  backupperPlanFiles = lib.mapAttrs (
    planName: plan:
    jsonFormat.generate "backupper-${planName}.json" (backupperPlanConfig planName plan)
  ) backupperPlans;
  gameBackuperPackage =
    inputs.game-backuper.packages.${pkgs.stdenv.hostPlatform.system}.game-backuper;
  mkGameBackuperCommand =
    planName: planFile:
    pkgs.writeShellApplication {
      name = "game-backuper-${planName}";
      runtimeInputs = [ gameBackuperPackage ];
      text = ''
        if [ "$#" -eq 0 ]; then
          exec game-backuper inspect --config ${planFile}
        fi

        case "$1" in
          inspect|plan|write|verify|launch-live|catalog-locate|catalog-show-tape|restore-archive|restore-member)
            command="$1"
            shift
            exec game-backuper "$command" --config ${planFile} "$@"
            ;;
          *)
            exec game-backuper "$@"
            ;;
        esac
      '';
    };
  gameBackuperCommands = lib.mapAttrs mkGameBackuperCommand gameBackuperPlanFiles;
  backupperPlanRendered = lib.mapAttrs backupperPlanConfig backupperPlans;
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
  };

  boot.kernelModules = [
    "sg"
    "st"
  ];

  environment.etc =
    lib.optionalAttrs (yatmConfigFile != null) {
      "yatm/config.yaml".source = yatmConfigFile;
    }
    // lib.mapAttrs' (
    planName: planFile: lib.nameValuePair "backupper/plans/${planName}.json" { source = planFile; }
  ) backupperPlanFiles
  // lib.mapAttrs' (
    planName: planFile: lib.nameValuePair "game-backuper/plans/${planName}.yaml" { source = planFile; }
  ) gameBackuperPlanFiles;

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
      ltfsDefault2
      ltfsOpen
      mt1WithDefaults
      mt2WithDefaults
      sg3_utils
      stfs
      tapelibPackage
      tapeDefault
      tapeDefault2
      backupper
      backupperRunner
      mtWithDefaults
      mtxWithDefaults
    ])
    ++ lib.optionals (selectedLtfsManagerPackage != null) [ selectedLtfsManagerPackage ]
    ++ lib.optionals (gameBackuperPlans != { }) (
      [ gameBackuperPackage ] ++ lib.attrValues gameBackuperCommands
    );

  systemd.services =
    (lib.mapAttrs' (
      planName: rendered:
      lib.nameValuePair "backupper-${planName}" {
        description = "Run backupper LTFS plan ${planName}";
        after = [ "local-fs.target" ];
        path = [
          backupperRunner
          changerDefault
          ltfsOpen
          mtWithDefaults
          mtxWithDefaults
          pkgs.findutils
          pkgs.fuse
          pkgs.fuse3
          pkgs.lsof
          pkgs.sqlite
          pkgs.systemd
          pkgs.sg3_utils
          pkgs.util-linux
          tapelibPackage
        ];
        environment = {
          PYTHONUNBUFFERED = "1";
        };
        serviceConfig = {
          Type = "simple";
          ExecStart = "${lib.getExe backupperRunner} --config /etc/backupper/plans/${planName}.json";
          Restart = "no";
          StandardOutput = "journal";
          StandardError = "journal";
          TimeoutStartSec = "infinity";
          WorkingDirectory = "/";
        };
      }
    ) backupperPlanRendered)
    // (lib.mapAttrs' (
      planName: command:
      lib.nameValuePair "game-backuper-${planName}" {
        description = "Run game-backuper live tape backup for ${planName}";
        path = [
          gameBackuperPackage
          mtWithDefaults
          mtxWithDefaults
        ];
        environment = {
          PYTHONUNBUFFERED = "1";
        };
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${command}/bin/game-backuper-${planName} write --backend live";
          StandardOutput = "journal";
          StandardError = "journal";
          TimeoutStartSec = "infinity";
          WorkingDirectory = "/";
        };
      }
    ) gameBackuperCommands);

  systemd.tmpfiles.rules =
    (lib.flatten (
      lib.mapAttrsToList (
        _planName: rendered:
        let
          stateDir = rendered.stateDir;
          databaseDir = builtins.dirOf rendered.database.path;
          backupDir = rendered.database.backupDir;
          statusDir = "${stateDir}/status";
          cacheDir = rendered.cache.path;
          mountDirs = map (drive: drive.mountPath) rendered.library.drives;
        in
        [
          "d ${stateDir} 0750 root root - -"
          "d ${databaseDir} 0750 root root - -"
          "d ${backupDir} 0750 root root - -"
          "d ${statusDir} 0750 root root - -"
          "d ${cacheDir} 0750 root root - -"
        ]
        ++ map (mountDir: "d ${mountDir} 0750 root root - -") mountDirs
      ) backupperPlanRendered
    ))
    ++ (lib.flatten (
      lib.mapAttrsToList (
        planName: plan:
        let
          runtimeRoot = "/var/lib/game-backuper/${planName}";
          catalogRoot =
            if plan ? catalog && plan.catalog ? sqlite_path then
              builtins.dirOf plan.catalog.sqlite_path
            else
              runtimeRoot;
        in
        [
          "d ${runtimeRoot} 0750 root root - -"
          "d ${catalogRoot} 0750 root root - -"
        ]
      ) gameBackuperPlans
    ));
}
