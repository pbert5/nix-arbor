{ config, lib, pkgs, ... }:
let
  cfg = config.services.fossilsafe;
  settingsFormat = pkgs.formats.json { };

  defaultPort = 5001;

  renderedSettings = lib.recursiveUpdate
    {
      allowed_origins = [
        "http://127.0.0.1:${toString defaultPort}"
        "http://localhost:${toString defaultPort}"
      ];
      backend_bind = "127.0.0.1";
      backend_port = defaultPort;
      catalog_backup_dir = "${cfg.stateDir}/catalog-backups";
      credential_key_path = "${cfg.stateDir}/credential_key.bin";
      db_path = "${cfg.stateDir}/lto_backup.db";
      diagnostics_dir = "${cfg.stateDir}/diagnostics";
      headless = false;
      staging_dir = "${cfg.stateDir}/staging";
    }
    cfg.settings;

  backendBind = renderedSettings.backend_bind or "127.0.0.1";
  backendPort = renderedSettings.backend_port or defaultPort;

  configFile = settingsFormat.generate "fossilsafe-config.json" renderedSettings;
  bootstrapFile =
    if cfg.bootstrap == { } then
      null
    else
      settingsFormat.generate "fossilsafe-bootstrap.json" cfg.bootstrap;
in
{
  options.services.fossilsafe = {
    enable = lib.mkEnableOption "FossilSafe tape library service";

    package = lib.mkOption {
      type = lib.types.nullOr lib.types.package;
      default = null;
      description = "FossilSafe package to run for the service and CLI.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Open the configured backend TCP port in the firewall.";
    };

    requireApiKey = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Require the configured FossilSafe API key for API requests.";
    };

    skipHardwareInit = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Skip hardware communication checks at startup. The service will start and
        serve the web UI in no-hardware mode. Useful during development when the
        tape library is unavailable or in a bad state.
      '';
    };

    stateDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/fossilsafe";
      description = "Persistent state directory for FossilSafe data and runtime files.";
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "fossilsafe";
      description = "System user that runs FossilSafe.";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "fossilsafe";
      description = "Primary system group for the FossilSafe service user.";
    };

    settings = lib.mkOption {
      type = settingsFormat.type;
      default = { };
      example = lib.literalExpression ''
        {
          tape = {
            changer_device = "/dev/tape/by-id/REPLACE_ME";
            drive_device = "/dev/tape/by-id/REPLACE_ME";
            drive_devices = [ "/dev/tape/by-id/REPLACE_ME" ];
            mtx_unload_order = "drive_slot";
          };
        }
      '';
      description = "Canonical FossilSafe config rendered to /etc/fossilsafe/config.json.";
    };

    bootstrap = lib.mkOption {
      type = settingsFormat.type;
      default = { };
      example = lib.literalExpression ''
        {
          oidc = {
            enabled = false;
          };
          settings = {
            verification_enabled = true;
          };
          sources = [
            {
              id = "games-library";
              name = "Games Library";
              source_type = "local";
              source_path = "/srv/games";
            }
          ];
          schedules = [
            {
              name = "Games Weekly";
              source_id = "games-library";
              cron = "0 30 3 * * 0";
              enabled = false;
            }
          ];
        }
      '';
      description = "Declarative catalog bootstrap applied before FossilSafe starts.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.package != null;
        message = "services.fossilsafe.package must be set when FossilSafe is enabled.";
      }
    ];

    environment.etc."fossilsafe/config.json".source = configFile;

    networking.firewall.allowedTCPPorts = lib.optionals cfg.openFirewall [ backendPort ];

    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir} 0750 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/catalog-backups 0750 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/diagnostics 0750 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/hooks.d 0750 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/staging 0750 ${cfg.user} ${cfg.group} - -"
      "d ${cfg.stateDir}/tmp 0750 ${cfg.user} ${cfg.group} - -"
    ];

    users.groups.${cfg.group} = { };

    users.users.${cfg.user} = {
      createHome = true;
      extraGroups = [ "tape" ];
      group = cfg.group;
      home = cfg.stateDir;
      isSystemUser = true;
    };

    systemd.services.fossilsafe = {
      description = "FossilSafe tape archive service";
      after = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];

      environment = {
        FOSSILSAFE_BACKEND_BIND = toString backendBind;
        FOSSILSAFE_BACKEND_PORT = toString backendPort;
        FOSSILSAFE_CATALOG_BACKUP_DIR = "${cfg.stateDir}/catalog-backups";
        FOSSILSAFE_CONFIG_PATH = "/etc/fossilsafe/config.json";
        FOSSILSAFE_DATA_DIR = cfg.stateDir;
        FOSSILSAFE_DIAGNOSTICS_DIR = "${cfg.stateDir}/diagnostics";
        FOSSILSAFE_HOOKS_DIR = "${cfg.stateDir}/hooks.d";
        FOSSILSAFE_REQUIRE_API_KEY = if cfg.requireApiKey then "true" else "false";
        FOSSILSAFE_SKIP_HARDWARE_INIT = if cfg.skipHardwareInit then "1" else "0";
        FOSSILSAFE_STATE_PATH = "${cfg.stateDir}/state.json";
        FOSSILSAFE_VAR_DIR = "${cfg.stateDir}/tmp";
        HOME = cfg.stateDir;
      };

      serviceConfig = {
        ExecStartPre = lib.optional (bootstrapFile != null) "${lib.getExe' cfg.package "fossilsafe-bootstrap"} ${bootstrapFile}";
        ExecStart = lib.getExe cfg.package;
        Group = cfg.group;
        Restart = "on-failure";
        RestartSec = "10s";
        SupplementaryGroups = [ "tape" ];
        User = cfg.user;
        WorkingDirectory = cfg.stateDir;
      };
    };
  };
}
