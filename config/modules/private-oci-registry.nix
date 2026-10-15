{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.arbor.ci.privateRegistry;
  poolRoot = "/mypool";
  registryRoot = "${poolRoot}/oci-registry";
  registryPort = 5100;
  readerPort = 5101;
  writerPort = 5102;
  readerAuth = "/run/secrets/private-oci-registry/pull.htpasswd";
  writerAuth = "/run/secrets/private-oci-registry/push.htpasswd";
  storageUnit = "private-oci-registry-storage";
  storageService = "${storageUnit}.service";
in
{
  options.arbor.ci.privateRegistry.enable = lib.mkEnableOption "private OCI registry for trusted CI";

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = config.services.tailscale.enable;
        message = "arbor.ci.privateRegistry requires Tailscale to be enabled";
      }
    ];

    services.dockerRegistry = {
      enable = true;
      listenAddress = "127.0.0.1";
      port = registryPort;
      openFirewall = false;
      storagePath = "${registryRoot}/data";
      enableDelete = true;
      # GC is an explicit operator operation after a dry run. The upstream
      # module's scheduled GC has no retention policy and is disabled here.
      enableGarbageCollect = false;
      extraConfig.http.relativeurls = true;
    };

    services.nginx = {
      enable = true;
      virtualHosts."private-oci-registry-reader" = {
        listen = [
          {
            addr = "127.0.0.1";
            port = readerPort;
          }
        ];
        locations."/v2/" = {
          extraConfig = ''
            auth_basic "private OCI registry pull";
            auth_basic_user_file ${readerAuth};
            limit_except GET HEAD { deny all; }
            proxy_pass http://127.0.0.1:${toString registryPort};
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_request_buffering off;
            client_max_body_size 0;
          '';
        };
      };
      virtualHosts."private-oci-registry-writer" = {
        listen = [
          {
            addr = "127.0.0.1";
            port = writerPort;
          }
        ];
        locations."/v2/" = {
          extraConfig = ''
            auth_basic "private OCI registry push";
            auth_basic_user_file ${writerAuth};
            proxy_pass http://127.0.0.1:${toString registryPort};
            proxy_set_header Host $host;
            proxy_set_header X-Forwarded-Proto https;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_request_buffering off;
            client_max_body_size 0;
          '';
        };
      };
    };

    systemd.services.${storageUnit} = {
      description = "Prepare the private OCI registry on mounted mypool";
      before = [
        "docker-registry.service"
        "nginx.service"
      ];
      requiredBy = [
        "docker-registry.service"
        "nginx.service"
      ];
      after = [
        "zfs-import-mypool.service"
        "zfs-mount.service"
      ];
      requires = [
        "zfs-import-mypool.service"
        "zfs-mount.service"
      ];
      serviceConfig.Type = "oneshot";
      script = ''
        set -eu
        ${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}
        ${pkgs.coreutils}/bin/install -d -o docker-registry -g docker-registry -m 0750 ${registryRoot}/data
      '';
    };

    systemd.services.docker-registry = {
      requires = [ storageService ];
      after = [ storageService ];
      serviceConfig.ExecStartPre = "${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}";
    };
    systemd.services.nginx = {
      requires = [ storageService ];
      after = [
        storageService
        "docker-registry.service"
      ];
      serviceConfig.ExecStartPre = [
        "${pkgs.util-linux}/bin/mountpoint -q ${poolRoot}"
        "${pkgs.coreutils}/bin/test -s ${readerAuth}"
        "${pkgs.coreutils}/bin/test -s ${writerAuth}"
      ];
    };
    # Node-level Serve terminates HTTPS with the machine's Tailscale
    # certificate, then proxies HTTP over loopback. It manages only its two
    # owned ports rather than replacing the host's complete Serve config.
    systemd.services.tailscale-oci-registry-serve = {
      description = "Expose private OCI registry through Tailscale HTTPS";
      wantedBy = [ "multi-user.target" ];
      requires = [
        "nginx.service"
        "tailscaled.service"
      ];
      after = [
        "nginx.service"
        "tailscaled.service"
        "tailscaled-autoconnect.service"
      ];
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = pkgs.writeShellScript "tailscale-oci-registry-serve-start" ''
          set -eu
          ${lib.getExe config.services.tailscale.package} serve --https=443 --bg http://127.0.0.1:${toString readerPort}
          ${lib.getExe config.services.tailscale.package} serve --https=8443 --bg http://127.0.0.1:${toString writerPort}
        '';
        ExecStop = pkgs.writeShellScript "tailscale-oci-registry-serve-stop" ''
          ${lib.getExe config.services.tailscale.package} serve --https=8443 --yes off || true
          ${lib.getExe config.services.tailscale.package} serve --https=443 --yes off || true
        '';
      };
    };

    systemd.services.private-oci-registry-gc-dry-run = {
      description = "Preview OCI registry garbage collection";
      requires = [ storageService ];
      after = [ storageService ];
      serviceConfig = {
        Type = "oneshot";
        User = "docker-registry";
        ExecStart = "${lib.getExe config.services.dockerRegistry.package} garbage-collect --dry-run ${config.services.dockerRegistry.configFile}";
      };
    };

    networking.firewall.interfaces.tailscale0.allowedTCPPorts = [
      443
      8443
    ];
  };
}
