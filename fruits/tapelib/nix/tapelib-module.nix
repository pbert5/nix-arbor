{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.tapelib;
  jsonFormat = pkgs.formats.json { };

  renderedConfig = {
    stateDir = cfg.stateDir;
    library = {
      allowedGenerations = cfg.library.allowedGenerations;
      changerDevice = cfg.library.changerDevice;
      drives = cfg.library.drives;
    };
    cache = cfg.cache;
    fuse = cfg.fuse;
    database = cfg.database;
    webui = cfg.webui;
    games = cfg.games;
    archive = cfg.archive;
  };

  configFile = jsonFormat.generate "tapelib-config.json" renderedConfig;
  servicePath = with pkgs; [
    fuse
    fuse3
    lsof
    mtx
    python3
    sg3_utils
    sqlite
    util-linux
  ];
  servicePathBin = lib.makeBinPath servicePath;
in
{
  options.services.tapelib = {
    enable = lib.mkEnableOption "tapelib tape library overlay service";

    package = lib.mkOption {
      type = lib.types.nullOr lib.types.package;
      default = null;
      description = "tapelib package to run for the daemon, web service, and CLI.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Open the configured tapelib web TCP port in the firewall.";
    };

    stateDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/tapelib";
      description = "Persistent state directory for tapelib runtime files and manifests.";
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "tapelib";
      description = "System user that runs tapelib services.";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "tapelib";
      description = "Primary system group for tapelib services.";
    };

    library = {
      allowedGenerations = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ "L5" ];
        description = "Tape barcode generations tapelib will operate on for LTFS workflows.";
      };

      changerDevice = lib.mkOption {
        type = lib.types.nullOr lib.types.str;
        default = null;
        description = "Tape changer device path.";
      };

      drives = lib.mkOption {
        type = lib.types.listOf (
          lib.types.submodule {
            options = {
              name = lib.mkOption {
                type = lib.types.str;
                description = "Stable drive name.";
              };
              sgDevice = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "SCSI generic device path for the drive when known.";
              };
              stDevice = lib.mkOption {
                type = lib.types.str;
                description = "Non-rewinding tape device path.";
              };
              mountPath = lib.mkOption {
                type = lib.types.str;
                description = "LTFS mount path reserved for this drive.";
              };
            };
          }
        );
        default = [ ];
        description = "Declarative drive inventory for tapelib.";
      };
    };

    cache = {
      path = lib.mkOption {
        type = lib.types.str;
        default = "/run/media/ash/cache/tapelib";
        description = "Cache and write-inbox root.";
      };
      maxBytes = lib.mkOption {
        type = lib.types.str;
        default = "900G";
        description = "Soft maximum cache size used by planners and cleanup jobs.";
      };
      reservedFreeBytes = lib.mkOption {
        type = lib.types.str;
        default = "50G";
        description = "Reserved free-space floor for cache cleanup decisions.";
      };
    };

    archive = {
      smallFileBundleMaxBytes = lib.mkOption {
        type = lib.types.str;
        default = "0";
        description = "Bundle files at or below this size into tar archives before writing to LTFS. Set to 0 to disable bundling.";
      };
      smallFileBundleTargetBytes = lib.mkOption {
        type = lib.types.str;
        default = "256M";
        description = "Target tar bundle size used when grouping small archive files together.";
      };
    };

    fuse = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Mount the read-only tapelib FUSE browser surface.";
      };
      mountPoint = lib.mkOption {
        type = lib.types.str;
        default = "/mnt/tapelib";
        description = "FUSE overlay mountpoint.";
      };
      user = lib.mkOption {
        type = lib.types.str;
        default = "ash";
        description = "Intended foreground FUSE owner.";
      };
      group = lib.mkOption {
        type = lib.types.str;
        default = "users";
        description = "Intended foreground FUSE group.";
      };
    };

    database.path = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/tapelib/catalog.sqlite";
      description = "Catalog database path.";
    };

    webui = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Enable the lightweight JSON status web service.";
      };
      host = lib.mkOption {
        type = lib.types.str;
        default = "127.0.0.1";
        description = "Web service bind host.";
      };
      port = lib.mkOption {
        type = lib.types.port;
        default = 5001;
        description = "Web service bind port.";
      };
    };

    games = {
      sourceRoots = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [
          "/home/example/games/incoming"
          "/home/example/games/_source-archives"
        ];
        description = "Game archive roots that will be collapsed into one logical namespace.";
      };
      namespacePrefix = lib.mkOption {
        type = lib.types.str;
        default = "/games";
        description = "Logical prefix used when building tape manifests and plans.";
      };
      selectedTapes = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ ];
        description = "Ordered set of tapes reserved for multi-tape planning.";
      };
      tapeCapacityBytes = lib.mkOption {
        type = lib.types.int;
        default = 1400000000000;
        description = "Planning capacity per tape in bytes.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.package != null;
        message = "services.tapelib.package must be set when tapelib is enabled.";
      }
      {
        assertion = cfg.library.drives != [ ];
        message = "services.tapelib.library.drives must contain at least one tape drive.";
      }
    ];

    environment.etc."tapelib/config.json".source = configFile;
    environment.systemPackages = [ cfg.package ];
    networking.firewall.allowedTCPPorts = lib.optionals (cfg.openFirewall && cfg.webui.enable) [
      cfg.webui.port
    ];
    programs.fuse = lib.mkIf cfg.fuse.enable {
      enable = true;
      userAllowOther = true;
    };

    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir} 2770 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir} 2770 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/jobs 2770 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir}/jobs 2770 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/locks 2770 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir}/locks 2770 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/manifests 2770 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/mounts 2770 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/spool 2770 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/status 2770 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.database.path} 0660 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.database.path}-shm 0660 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.database.path}-wal 0660 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir}/status/cache-cleanup.json 0660 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir}/status/inventory.json 0660 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir}/status/latest-plan.json 0660 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir}/status/status.json 0660 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir}/status/TAPELIB-INVENTORY.json 0660 ${cfg.user} ${cfg.group} - -"
      "z ${cfg.stateDir}/status/verify.json 0660 ${cfg.user} ${cfg.group} - -"
    ]
    ++ builtins.map (
      drive: "d ${drive.mountPath} 2770 ${cfg.user} ${cfg.group} - -"
    ) cfg.library.drives;

    users.groups.${cfg.group} = { };

    users.users.${cfg.user} = {
      createHome = false;
      extraGroups = [ "tape" ];
      group = cfg.group;
      home = cfg.stateDir;
      isSystemUser = true;
    };

    users.users.${cfg.fuse.user}.extraGroups = [ cfg.group ];

    systemd.services.tapelibd = {
      description = "tapelib queue and state daemon";
      after = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];
      path = servicePath;
      environment = {
        HOME = cfg.stateDir;
        TAPELIB_CONFIG_PATH = "/etc/tapelib/config.json";
      };
      serviceConfig = {
        ExecStartPre = "${lib.getExe cfg.package} --config /etc/tapelib/config.json init-db";
        ExecStart = "${lib.getExe cfg.package} --config /etc/tapelib/config.json daemon";
        Group = cfg.group;
        Restart = "on-failure";
        RestartSec = "10s";
        SupplementaryGroups = [ "tape" ];
        UMask = "0007";
        User = cfg.user;
        WorkingDirectory = cfg.stateDir;
      };
    };

    systemd.services.tapelib-web = lib.mkIf cfg.webui.enable {
      description = "tapelib JSON status web service";
      after = [ "tapelibd.service" ];
      wantedBy = [ "multi-user.target" ];
      requires = [ "tapelibd.service" ];
      path = servicePath;
      environment = {
        HOME = cfg.stateDir;
        TAPELIB_CONFIG_PATH = "/etc/tapelib/config.json";
      };
      serviceConfig = {
        ExecStartPre = "${lib.getExe cfg.package} --config /etc/tapelib/config.json init-db";
        ExecStart = "${lib.getExe cfg.package} --config /etc/tapelib/config.json serve-web";
        Group = cfg.group;
        Restart = "on-failure";
        RestartSec = "10s";
        SupplementaryGroups = [ "tape" ];
        UMask = "0007";
        User = cfg.user;
        WorkingDirectory = cfg.stateDir;
      };
    };

    systemd.services.tapelib-fuse = lib.mkIf cfg.fuse.enable {
      description = "tapelib read-only FUSE browse mount";
      after = [ "tapelibd.service" ];
      wantedBy = [ "multi-user.target" ];
      requires = [ "tapelibd.service" ];
      environment = {
        HOME = cfg.stateDir;
        LD_LIBRARY_PATH = lib.makeLibraryPath [ pkgs.fuse ];
        PATH = lib.mkForce "/run/wrappers/bin:${servicePathBin}";
        TAPELIB_CONFIG_PATH = "/etc/tapelib/config.json";
      };
      serviceConfig = {
        ExecStartPre = [
          "+${pkgs.coreutils}/bin/install -d -m 0755 -o ${cfg.user} -g ${cfg.group} ${cfg.fuse.mountPoint}"
          "-/run/wrappers/bin/fusermount -u ${cfg.fuse.mountPoint}"
        ];
        ExecStart = "${lib.getExe cfg.package} --config /etc/tapelib/config.json mount-fuse --mount-point ${cfg.fuse.mountPoint} --allow-other";
        ExecStop = "-/run/wrappers/bin/fusermount -u ${cfg.fuse.mountPoint}";
        Group = cfg.group;
        Restart = "on-failure";
        RestartSec = "10s";
        SupplementaryGroups = [ "tape" ];
        UMask = "0007";
        User = cfg.user;
        WorkingDirectory = cfg.stateDir;
      };
    };

    systemd.services.tapelib-inventory = {
      description = "tapelib inventory refresh";
      path = servicePath;
      environment.TAPELIB_CONFIG_PATH = "/etc/tapelib/config.json";
      serviceConfig = {
        Type = "oneshot";
        User = cfg.user;
        Group = cfg.group;
        UMask = "0007";
        WorkingDirectory = cfg.stateDir;
        ExecStart = "${lib.getExe cfg.package} --config /etc/tapelib/config.json inventory --json --write-status";
      };
    };

    systemd.timers.tapelib-inventory = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "5m";
        OnUnitActiveSec = "30m";
        Unit = "tapelib-inventory.service";
      };
    };

    systemd.services.tapelib-cache-cleanup = {
      description = "tapelib cache cleanup scaffold";
      path = servicePath;
      environment.TAPELIB_CONFIG_PATH = "/etc/tapelib/config.json";
      serviceConfig = {
        Type = "oneshot";
        User = cfg.user;
        Group = cfg.group;
        UMask = "0007";
        WorkingDirectory = cfg.stateDir;
        ExecStart = "${lib.getExe cfg.package} --config /etc/tapelib/config.json cleanup-cache";
      };
    };

    systemd.timers.tapelib-cache-cleanup = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "20m";
        OnUnitActiveSec = "6h";
        Unit = "tapelib-cache-cleanup.service";
      };
    };

    systemd.services.tapelib-verify = {
      description = "tapelib verification scaffold";
      path = servicePath;
      environment.TAPELIB_CONFIG_PATH = "/etc/tapelib/config.json";
      serviceConfig = {
        Type = "oneshot";
        User = cfg.user;
        Group = cfg.group;
        UMask = "0007";
        WorkingDirectory = cfg.stateDir;
        ExecStart = "${lib.getExe cfg.package} --config /etc/tapelib/config.json verify";
      };
    };

    systemd.timers.tapelib-verify = {
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "30m";
        OnUnitActiveSec = "12h";
        Unit = "tapelib-verify.service";
      };
    };
  };
}
