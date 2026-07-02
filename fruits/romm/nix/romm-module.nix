{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.romm;
  containerBackend = config.virtualisation.oci-containers.backend;
  containerPrefix = if containerBackend == "podman" then "podman" else "docker";
  runtimeEnvironmentFile = "${cfg.stateDir}/secrets/runtime.env";
  secretsDir = "${cfg.stateDir}/secrets";
  dbDir = "${cfg.stateDir}/mariadb";
  assetsDir = "${cfg.stateDir}/assets";
  configDir = "${cfg.stateDir}/config";
  resourcesDir = "${cfg.stateDir}/resources";
in
{
  options.services.romm = {
    enable = lib.mkEnableOption "RomM game library manager";

    image = lib.mkOption {
      type = lib.types.str;
      default = "docker.io/rommapp/romm:latest";
      description = "OCI image used for the RomM application container.";
    };

    databaseImage = lib.mkOption {
      type = lib.types.str;
      default = "docker.io/library/mariadb:latest";
      description = "OCI image used for the RomM MariaDB container.";
    };

    stateDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/romm";
      description = "Root-backed state directory for RomM configuration, assets, database data, resources, and local secrets.";
    };

    libraryDir = lib.mkOption {
      type = lib.types.str;
      default = "/fast/GameLibrary";
      description = "Fast storage path mounted into RomM as its game library.";
    };

    providerEnvironmentFile = lib.mkOption {
      type = lib.types.str;
      default = "${cfg.stateDir}/secrets/providers.env";
      description = "Root-owned env file containing metadata provider credentials.";
    };

    scanWorkers = lib.mkOption {
      type = lib.types.ints.positive;
      default = 1;
      description = "Number of RomM worker processes for scan tasks.";
    };

    endpoint = lib.mkOption {
      type = lib.types.submodule {
        freeformType = lib.types.attrsOf lib.types.anything;
        options = {
          bind = lib.mkOption {
            type = lib.types.str;
            default = "0.0.0.0";
            description = "Host address passed to the container port publisher.";
          };
          port = lib.mkOption {
            type = lib.types.port;
            default = 8095;
            description = "Host TCP port that publishes RomM.";
          };
          url = lib.mkOption {
            type = lib.types.str;
            default = "http://0.0.0.0:8095";
            description = "External URL RomM should use for generated links and log messages.";
          };
        };
      };
      default = { };
      description = "RomM host endpoint.";
    };

    extraEnvironment = lib.mkOption {
      type = lib.types.attrsOf lib.types.str;
      default = { };
      description = "Additional non-secret RomM environment variables.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = containerBackend == "podman";
        message = "services.romm expects virtualisation.oci-containers.backend to be podman.";
      }
    ];

    virtualisation.podman.enable = true;
    virtualisation.oci-containers.backend = "podman";

    environment.systemPackages = [ pkgs.podman ];

    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir} 0750 root root - -"
      "d ${secretsDir} 0700 root root - -"
      # mariadb's official image runs mariadbd as the fixed mysql uid/gid 999;
      # creating this dir as root:root leaves mariadbd unable to read its own
      # datadir (table discovery silently fails, e.g. "Table 'romm.users' doesn't exist").
      "d ${dbDir} 0750 999 999 - -"
      "d ${assetsDir} 0755 root root - -"
      "d ${configDir} 0755 root root - -"
      "d ${resourcesDir} 0755 root root - -"
      "d ${cfg.libraryDir} 0755 root root - -"
    ];

    systemd.services.romm-secrets = {
      description = "Prepare local RomM secrets";
      wantedBy = [ "multi-user.target" ];
      before = [
        "${containerPrefix}-romm.service"
        "${containerPrefix}-romm-db.service"
      ];
      requiredBy = [
        "${containerPrefix}-romm.service"
        "${containerPrefix}-romm-db.service"
      ];
      after = [ "systemd-tmpfiles-setup.service" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      path = [
        pkgs.coreutils
        pkgs.openssl
      ];
      script = ''
        set -euo pipefail

        install -d -m 0700 -o root -g root ${lib.escapeShellArg secretsDir}

        if [ ! -s ${lib.escapeShellArg runtimeEnvironmentFile} ]; then
          umask 077
          db_password="$(openssl rand -base64 36 | tr -d '\n')"
          mariadb_root_password="$(openssl rand -base64 36 | tr -d '\n')"
          auth_secret="$(openssl rand -hex 32 | tr -d '\n')"

          {
            printf 'MARIADB_ROOT_PASSWORD=%s\n' "$mariadb_root_password"
            printf 'MARIADB_PASSWORD=%s\n' "$db_password"
            printf 'DB_PASSWD=%s\n' "$db_password"
            printf 'ROMM_AUTH_SECRET_KEY=%s\n' "$auth_secret"
          } > ${lib.escapeShellArg runtimeEnvironmentFile}
        fi

        if [ ! -e ${lib.escapeShellArg cfg.providerEnvironmentFile} ]; then
          umask 077
          : > ${lib.escapeShellArg cfg.providerEnvironmentFile}
        fi
      '';
    };

    systemd.services.romm-podman-network = {
      description = "Prepare the RomM Podman network";
      wantedBy = [ "multi-user.target" ];
      before = [
        "${containerPrefix}-romm.service"
        "${containerPrefix}-romm-db.service"
      ];
      requiredBy = [
        "${containerPrefix}-romm.service"
        "${containerPrefix}-romm-db.service"
      ];
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      path = [ pkgs.podman ];
      script = ''
        set -euo pipefail

        if ! podman network exists romm; then
          podman network create romm
        fi
      '';
    };

    virtualisation.oci-containers.containers = {
      romm-db = {
        image = cfg.databaseImage;
        pull = "newer";
        environment = {
          MARIADB_DATABASE = "romm";
          MARIADB_USER = "romm-user";
        };
        environmentFiles = [ runtimeEnvironmentFile ];
        volumes = [ "${dbDir}:/var/lib/mysql" ];
        networks = [ "romm" ];
        extraOptions = [
          "--network-alias=romm-db"
          "--health-cmd=healthcheck.sh --connect --innodb_initialized"
          "--health-start-period=30s"
          "--health-interval=10s"
          "--health-timeout=5s"
          "--health-retries=5"
        ];
      };

      romm = {
        image = cfg.image;
        pull = "newer";
        dependsOn = [ "romm-db" ];
        environment = {
          DB_HOST = "romm-db";
          DB_NAME = "romm";
          DB_USER = "romm-user";
          ROMM_PORT = "8080";
          ROMM_BASE_URL = cfg.endpoint.url;
          SCAN_WORKERS = toString cfg.scanWorkers;
          TZ = config.time.timeZone or "UTC";
        }
        // cfg.extraEnvironment;
        environmentFiles = [
          runtimeEnvironmentFile
          cfg.providerEnvironmentFile
        ];
        ports = [ "${cfg.endpoint.bind}:${toString cfg.endpoint.port}:8080" ];
        volumes = [
          "${resourcesDir}:/romm/resources"
          "${cfg.libraryDir}:/romm/library"
          "${assetsDir}:/romm/assets"
          "${configDir}:/romm/config"
        ];
        networks = [ "romm" ];
        extraOptions = [ "--network-alias=romm" ];
      };
    };

    systemd.services."${containerPrefix}-romm-db" = {
      requires = [
        "romm-secrets.service"
        "romm-podman-network.service"
      ];
      after = [
        "romm-secrets.service"
        "romm-podman-network.service"
      ];
      unitConfig.RequiresMountsFor = [
        cfg.stateDir
      ];
    };

    systemd.services."${containerPrefix}-romm" = {
      requires = [
        "romm-secrets.service"
        "romm-podman-network.service"
      ];
      after = [
        "romm-secrets.service"
        "romm-podman-network.service"
        "${containerPrefix}-romm-db.service"
      ];
      unitConfig.RequiresMountsFor = [
        cfg.stateDir
        cfg.libraryDir
      ];
    };
  };
}
