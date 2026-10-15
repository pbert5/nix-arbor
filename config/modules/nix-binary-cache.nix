{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.arbor.nixBinaryCache;
  poolRoot = "/mypool";
  cacheRoot = "${poolRoot}/nix-binary-cache";
  databaseRoot = "${cacheRoot}/database";
  storageService = "arbor-nix-binary-cache-storage";
in
{
  options.arbor.nixBinaryCache = {
    enable = lib.mkEnableOption "the optional Attic Nix binary cache";

    endpoint = lib.mkOption {
      type = lib.types.str;
      default = "https://nix-cache.invalid/";
      description = "Canonical private HTTPS Attic API endpoint supplied by integration.";
    };

    allowedHosts = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ "nix-cache.invalid" ];
      description = "Exact Host header values accepted by Attic; integration must set the private cache host.";
    };

    listenAddress = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1:8088";
      description = "Attic API bind address; keep loopback behind private HTTPS ingress.";
    };

    environmentFile = lib.mkOption {
      type = lib.types.str;
      default = "/run/secrets/attic-server.env";
      description = "Runtime-only Attic JWT signing secret file, outside the Nix store.";
    };

    retentionPeriod = lib.mkOption {
      type = lib.types.str;
      default = "90 days";
      description = "Maximum age of unaccessed cache data before Attic GC can remove it.";
    };
  };

  config = lib.mkIf cfg.enable {
    services.atticd = {
      enable = true;
      inherit (cfg) environmentFile;
      settings = {
        listen = cfg.listenAddress;
        "api-endpoint" = cfg.endpoint;
        # Require an explicit canonical host. The deployment owner must replace
        # this placeholder alongside endpoint and TLS ingress.
        "allowed-hosts" = cfg.allowedHosts;
        database.url = "sqlite:///${databaseRoot}/server.db?mode=rwc";
        storage = {
          type = "local";
          path = "${cacheRoot}/storage";
        };
        chunking = {
          nar-size-threshold = 65536;
          min-size = 16384;
          avg-size = 65536;
          max-size = 262144;
        };
        compression.type = "zstd";
        "garbage-collection" = {
          interval = "1 day";
          "default-retention-period" = cfg.retentionPeriod;
        };
      };
    };

    users.groups.atticd = { };
    users.users.atticd = {
      isSystemUser = true;
      group = "atticd";
    };

    # This service deliberately fails when mypool is absent. No directory is
    # ever created at /mypool on the root filesystem as a fallback.
    systemd.services.${storageService} = {
      description = "Prepare guarded mypool storage for the optional Nix cache";
      wantedBy = [ "multi-user.target" ];
      after = [
        "zfs-import-mypool.service"
        "zfs-mount.service"
      ];
      requires = [
        "zfs-import-mypool.service"
        "zfs-mount.service"
      ];
      before = [ "atticd.service" ];
      serviceConfig.Type = "oneshot";
      script = ''
        set -eu
        ${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}
        ${pkgs.coreutils}/bin/install -d -o root -g root -m 0711 ${cacheRoot}
        ${pkgs.coreutils}/bin/install -d -o atticd -g atticd -m 0700 ${cacheRoot}/database
        ${pkgs.coreutils}/bin/install -d -o atticd -g atticd -m 0700 ${cacheRoot}/storage
      '';
    };

    systemd.services.atticd = {
      requires = [ storageService ];
      after = [ storageService ];
      serviceConfig = {
        DynamicUser = lib.mkForce false;
        User = "atticd";
        Group = "atticd";
        ExecStartPre = "${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}";
        # The upstream unit only allows writes under storage.path. SQLite
        # needs its separate database directory exposed through ProtectSystem.
        ReadWritePaths = lib.mkAfter [ databaseRoot ];
      };
    };

    assertions = [
      {
        assertion = !lib.hasPrefix "/nix/store/" cfg.environmentFile;
        message = "Attic's runtime secret file must stay outside the Nix store";
      }
      {
        assertion = lib.hasPrefix "https://" cfg.endpoint;
        message = "Attic's canonical endpoint must use HTTPS";
      }
      {
        assertion = cfg.listenAddress == "127.0.0.1:8088";
        message = "Attic must bind to loopback until a reviewed private HTTPS ingress is integrated";
      }
      {
        assertion = config.services.atticd.settings.storage.path == "${cacheRoot}/storage";
        message = "Attic cache storage must remain under the guarded mypool path";
      }
    ];
  };
}
