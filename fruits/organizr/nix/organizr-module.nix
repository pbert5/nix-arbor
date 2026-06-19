{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.organizr;
  containerBackend = config.virtualisation.oci-containers.backend;
  containerPrefix = if containerBackend == "podman" then "podman" else "docker";
  setupHost =
    if cfg.endpoint.bind == "0.0.0.0" || cfg.endpoint.bind == "::" then
      "127.0.0.1"
    else
      cfg.endpoint.bind;
  setupBaseUrl = "http://${setupHost}:${toString cfg.endpoint.port}";
  organizrConfigFile = "${cfg.stateDir}/www/organizr/data/config/config.php";
in
{
  options.services.organizr = {
    enable = lib.mkEnableOption "Organizr home lab dashboard";

    image = lib.mkOption {
      type = lib.types.str;
      default = "ghcr.io/organizr/organizr:latest";
      description = "OCI image for the Organizr container.";
    };

    stateDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/organizr";
      description = "Directory for Organizr persistent configuration.";
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Open the configured Organizr TCP port in the host firewall.";
    };

    puid = lib.mkOption {
      type = lib.types.int;
      default = 911;
      description = "User ID the Organizr process runs as inside the container.";
    };

    pgid = lib.mkOption {
      type = lib.types.int;
      default = 911;
      description = "Group ID the Organizr process runs as inside the container.";
    };

    endpoint = lib.mkOption {
      type = lib.types.submodule {
        freeformType = lib.types.attrsOf lib.types.anything;
        options = {
          bind = lib.mkOption {
            type = lib.types.str;
            default = "0.0.0.0";
            description = "Host address to bind the published port.";
          };
          port = lib.mkOption {
            type = lib.types.port;
            default = 9983;
            description = "Host TCP port that publishes Organizr.";
          };
        };
      };
      default = { };
      description = "Organizr host endpoint.";
    };

    setup = lib.mkOption {
      type = lib.types.submodule {
        options = {
          enable = lib.mkOption {
            type = lib.types.bool;
            default = false;
            description = "Run the first-time Organizr setup wizard declaratively.";
          };

          installType = lib.mkOption {
            type = lib.types.enum [
              "personal"
              "business"
            ];
            default = "personal";
            description = "Organizr install type used by the first-time setup wizard.";
          };

          dbName = lib.mkOption {
            type = lib.types.str;
            default = "organizr";
            description = "SQLite database name passed to the first-time setup wizard.";
          };

          dbPath = lib.mkOption {
            type = lib.types.str;
            default = "/config/www/organizr/data/db";
            description = "Container-internal SQLite database directory passed to the first-time setup wizard.";
          };

          admin = {
            username = lib.mkOption {
              type = lib.types.str;
              default = "admin";
              description = "Initial Organizr admin username.";
            };

            email = lib.mkOption {
              type = lib.types.str;
              default = "admin@localhost";
              description = "Initial Organizr admin email.";
            };

            passwordSeed = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = "Seed material used to derive the initial Organizr admin password.";
            };

            passwordFile = lib.mkOption {
              type = lib.types.str;
              default = "${cfg.stateDir}/secrets/admin-password";
              description = "Root-only file where the derived initial Organizr admin password is stored.";
            };
          };
        };
      };
      default = { };
      description = "Declarative first-time setup wizard settings.";
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = containerBackend == "podman";
        message = "services.organizr expects virtualisation.oci-containers.backend to be podman.";
      }
      {
        assertion = cfg.puid != 0 && cfg.pgid != 0;
        message = "services.organizr.puid and services.organizr.pgid must be non-root because the container's PHP-FPM refuses to run as root.";
      }
      {
        assertion = !cfg.setup.enable || cfg.setup.admin.passwordSeed != null;
        message = "services.organizr.setup.admin.passwordSeed must be set when declarative setup is enabled.";
      }
    ];

    virtualisation.podman.enable = true;
    virtualisation.oci-containers.backend = "podman";

    environment.systemPackages = [ pkgs.podman ];

    networking.firewall.allowedTCPPorts = lib.optionals cfg.openFirewall [ cfg.endpoint.port ];

    systemd.tmpfiles.rules = [
      "d ${cfg.stateDir} 0755 root root - -"
      "z ${cfg.stateDir} 0755 root root - -"
      "d ${cfg.stateDir}/secrets 0700 root root - -"
    ];

    virtualisation.oci-containers.containers.organizr = {
      image = cfg.image;
      pull = "newer";
      environment = {
        PUID = toString cfg.puid;
        PGID = toString cfg.pgid;
        TZ = config.time.timeZone or "UTC";
      };
      ports = [ "${cfg.endpoint.bind}:${toString cfg.endpoint.port}:80" ];
      volumes = [ "${cfg.stateDir}:/config" ];
    };

    systemd.services."${containerPrefix}-organizr" = {
      unitConfig.RequiresMountsFor = [ cfg.stateDir ];
    };

    systemd.services.organizr-setup = lib.mkIf cfg.setup.enable {
      description = "Run first-time Organizr setup";
      after = [
        "${containerPrefix}-organizr.service"
        "network-online.target"
      ];
      requires = [ "${containerPrefix}-organizr.service" ];
      wants = [ "network-online.target" ];
      path = [
        pkgs.coreutils
        pkgs.curl
        pkgs.gnugrep
      ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      script = ''
        set -euo pipefail

        config_file=${lib.escapeShellArg organizrConfigFile}
        password_file=${lib.escapeShellArg cfg.setup.admin.passwordFile}

        if [ -s "$config_file" ]; then
          echo "Organizr config already exists at $config_file; skipping first-time setup."
          exit 0
        fi

        install -d -m 0700 -o root -g root "$(dirname "$password_file")"

        if [ ! -s "$password_file" ]; then
          password_seed=${lib.escapeShellArg cfg.setup.admin.passwordSeed}
          seed_hash="$(printf '%s' "$password_seed" | sha256sum | cut -d ' ' -f1)"
          admin_password="organizr-$(printf '%s' "$seed_hash" | cut -c1-32)"
          umask 077
          printf '%s\n' "$admin_password" > "$password_file"
        fi

        chmod 0600 "$password_file"
        admin_password="$(cat "$password_file")"
        seed_hash="$(printf '%s' "$admin_password" | sha256sum | cut -d ' ' -f1)"
        hash_key="$(printf '%s' "hash-$seed_hash" | sha256sum | cut -c1-30)"
        api_key="$(printf '%s' "api-$seed_hash" | sha256sum | cut -c1-20)"
        registration_password="organizr-registration-$(printf '%s' "registration-$seed_hash" | sha256sum | cut -c1-24)"

        for attempt in $(seq 1 150); do
          if curl -fsS -o /dev/null ${lib.escapeShellArg "${setupBaseUrl}/"}; then
            break
          fi

          if [ "$attempt" -eq 150 ]; then
            echo "Timed out waiting for Organizr to become ready at ${setupBaseUrl}." >&2
            exit 1
          fi

          sleep 2
        done

        response="$(
          curl -fsS \
            -X POST \
            --data-urlencode driver=sqlite3 \
            --data-urlencode dbName=${lib.escapeShellArg cfg.setup.dbName} \
            --data-urlencode dbPath=${lib.escapeShellArg cfg.setup.dbPath} \
            --data-urlencode license=${lib.escapeShellArg cfg.setup.installType} \
            --data-urlencode hashKey="$hash_key" \
            --data-urlencode api="$api_key" \
            --data-urlencode registrationPassword="$registration_password" \
            --data-urlencode username=${lib.escapeShellArg cfg.setup.admin.username} \
            --data-urlencode password="$admin_password" \
            --data-urlencode email=${lib.escapeShellArg cfg.setup.admin.email} \
            ${lib.escapeShellArg "${setupBaseUrl}/api/v2/wizard"}
        )"

        echo "$response" | grep -Eq '"result"[[:space:]]*:[[:space:]]*"success"'

        if [ ! -s "$config_file" ]; then
          echo "Organizr setup API returned success but $config_file was not created." >&2
          exit 1
        fi

        echo "Organizr first-time setup completed for ${cfg.setup.admin.username}."
      '';
    };

    systemd.timers.organizr-setup = lib.mkIf cfg.setup.enable {
      description = "Retry first-time Organizr setup until it has completed";
      wantedBy = [ "timers.target" ];
      timerConfig = {
        OnBootSec = "30s";
        OnUnitActiveSec = "5m";
        Unit = "organizr-setup.service";
      };
    };
  };
}
