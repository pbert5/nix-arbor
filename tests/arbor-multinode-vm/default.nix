{ inputs, pkgs }:

let
  lib = pkgs.lib;
  registry = inputs.arbor-registry;
  manager = inputs.arbor-manager;
  runtime = registry.packages.${pkgs.system}.arbor-registry-runtime;
  transport = registry.packages.${pkgs.system}.arbor-registry-transport;
  managerCli = manager.packages.${pkgs.system}.arbor-manager;
  pythonRuntime = pkgs.python3.withPackages (ps: [ ps.pynacl ]);
  transportRealmId = "arbor-acceptance-vm-realm-v1";

  topology = {
    root-a = {
      targetHost = "10.42.0.12";
      children = [ "child" ];
      criticalRoute = true;
    };
    root-b = {
      targetHost = "10.42.0.11";
      children = [ "child" ];
      state = "standby";
    };
    child = {
      targetHost = "10.42.0.12";
      parents = [
        "root-a"
        "root-b"
      ];
      children = [ "grandchild" ];
      criticalRoute = true;
    };
    grandchild = {
      targetHost = "10.42.0.13";
      parents = [ "child" ];
    };
  };
  plan = manager.lib.plan {
    nodes = topology;
    roots = [ "root-a" ];
    selector = "descendants";
    backend = "direct";
    batchSize = 1;
  };
  snapshot = manager.lib.snapshot.exportDeployment { inherit plan; };

  nodeModule =
    {
      hostname,
      address,
      bootstrap ? [ ],
      withVault ? false,
    }:
    lib.mkMerge [
      {
        imports = lib.optional withVault registry.nixosModules.vault-runtime-upstream;

        system.stateVersion = "25.05";
        networking = {
          hostName = hostname;
          useDHCP = false;
          firewall.enable = false;
          interfaces.eth1.ipv4.addresses = [
            {
              inherit address;
              prefixLength = 24;
            }
          ];
        };
        virtualisation.memorySize = 1536;

        services.openssh = {
          enable = true;
          settings = {
            PermitRootLogin = "yes";
            PasswordAuthentication = false;
          };
        };

        environment.systemPackages = [
          pkgs.curl
          pkgs.jq
          pkgs.iptables
          pkgs.openssh
          pkgs.openbao
          pythonRuntime
          pkgs.nixos-rebuild
          managerCli
          runtime
          transport
        ];
        environment.etc."arbor-test/scenario.py".source = ./scenario.py;
        environment.etc."arbor-test/accepted.py".source = ./accepted.py;
        environment.etc."arbor-test/list.py".source = ./list.py;
        environment.etc."arbor-test/status.py".source = ./status.py;
        environment.etc."arbor-test/append.py".source = ./append.py;
        environment.etc."arbor-test/snapshot.json".text = snapshot;
        environment.variables.PYTHONPATH = "${registry}/runtime";

        systemd.tmpfiles.rules = [
          "d /run/arbor-test 0700 root root -"
          "d /var/lib/arbor-registryd 0700 root root -"
        ];

        systemd.services.arbor-registryd = {
          description = "Arbor Registry acceptance transport daemon";
          wantedBy = [ "multi-user.target" ];
          serviceConfig = {
            Type = "simple";
            Restart = "on-failure";
            RestartSec = 2;
            ExecStartPre = "${pkgs.bash}/bin/bash -c 'install -d -m 0700 /run/arbor-test; test -s /run/arbor-test/registry.token || (umask 077; ${pkgs.coreutils}/bin/head -c 32 /dev/urandom | ${pkgs.coreutils}/bin/base64 -w0 > /run/arbor-test/registry.token)'";
            ExecStart = "${pkgs.bash}/bin/bash -c 'token=$(${pkgs.coreutils}/bin/cat /run/arbor-test/registry.token); export ARBOR_REGISTRY_SOCKET_TOKEN=\"$token\"; exec ${transport}/bin/arbor-registryd'";
            Environment = [
              "ARBOR_REGISTRY_STATE_DIR=/var/lib/arbor-registryd"
              "ARBOR_REGISTRY_SOCKET=/run/arbor-registryd/registry.sock"
              "ARBOR_REGISTRY_LISTEN=/ip4/0.0.0.0/tcp/4001"
              "ARBOR_REGISTRY_REALM_ID=${transportRealmId}"
              "ARBOR_REGISTRY_PROTOCOL_EPOCH=1"
              "ARBOR_REGISTRY_BOOTSTRAP_PEERS=${lib.concatStringsSep "," bootstrap}"
            ];
          };
        };

      }
      (lib.mkIf withVault {
        systemd.services.openbao-test = {
          wantedBy = [ "multi-user.target" ];
          serviceConfig = {
            Type = "simple";
            Restart = "on-failure";
            Environment = [ "HOME=/root" ];
            ExecStart = "${pkgs.openbao}/bin/bao server -dev -dev-root-token-id=arbor-test-root -dev-listen-address=0.0.0.0:8200";
          };
        };

        systemd.services.seed-openbao-secret = {
          wantedBy = [ "multi-user.target" ];
          after = [ "openbao-test.service" ];
          requires = [ "openbao-test.service" ];
          before = [ "arbor-vault-runtime-api-init.service" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
          };
          script = ''
            for attempt in $(seq 1 100); do
              if ${pkgs.curl}/bin/curl --fail --silent http://127.0.0.1:8200/v1/sys/health >/dev/null; then break; fi
              sleep 0.1
            done
            ${pkgs.curl}/bin/curl --fail --silent http://127.0.0.1:8200/v1/sys/health >/dev/null
            install -d -m 0700 /run/arbor-test
            printf '%s\n' arbor-test-root >/run/arbor-test/token
            chmod 0600 /run/arbor-test/token
            value=$(${pkgs.coreutils}/bin/head -c 24 /dev/urandom | ${pkgs.coreutils}/bin/base64 -w0)
            printf '%s' "$value" | ${pkgs.coreutils}/bin/sha256sum | ${pkgs.coreutils}/bin/cut -d' ' -f1 >/run/arbor-test/secret.sha256
            BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN=arbor-test-root \
              ${pkgs.openbao}/bin/bao kv put secret/arbor/acceptance value="$value" >/dev/null
          '';
        };

        cluster.vault.runtime = {
          enable = true;
          useUpstreamVaultd = true;
          useProviderBridge = true;
          runtimePackage = runtime;
          refreshInterval = 1;
          providers.local = {
            address = "http://127.0.0.1:8200";
            authMethod = "external";
            tokenFile = "/run/arbor-test/token";
          };
          requirements.acceptance = {
            provider = "local";
            path = "secret/data/arbor/acceptance";
            field = "value";
            credentialName = "acceptance-value";
          };
          bindings.api = {
            requirement = "acceptance";
            service = "arbor-test-consumer";
          };
        };

        systemd.services.arbor-test-consumer = {
          wantedBy = [ "multi-user.target" ];
          serviceConfig = {
            Type = "oneshot";
            RemainAfterExit = true;
          };
          script = ''
            ${pkgs.coreutils}/bin/sha256sum "$CREDENTIALS_DIRECTORY/acceptance-value" | ${pkgs.coreutils}/bin/cut -d' ' -f1 >/run/arbor-test/consumer.sha256
          '';
        };
      })
    ];
in
pkgs.testers.nixosTest {
  name = "arbor-multinode-acceptance";

  nodes = {
    root-a = nodeModule {
      hostname = "root-a";
      address = "10.42.0.10";
    };
    root-b = nodeModule {
      hostname = "root-b";
      address = "10.42.0.11";
      bootstrap = [ "/ip4/10.42.0.10/tcp/4001" ];
    };
    child = nodeModule {
      hostname = "child";
      address = "10.42.0.12";
      bootstrap = [
        "/ip4/10.42.0.10/tcp/4001"
        "/ip4/10.42.0.11/tcp/4001"
      ];
      withVault = true;
    };
    grandchild = nodeModule {
      hostname = "grandchild";
      address = "10.42.0.13";
      bootstrap = [ "/ip4/10.42.0.12/tcp/4001" ];
    };
  };

  testScript = builtins.readFile ./test-script.py;
}
