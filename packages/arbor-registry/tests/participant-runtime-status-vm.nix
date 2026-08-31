{
  module,
  runtimeModule,
  pkgs,
}:
let
  runtimePackage = import ../runtime/package.nix {
    inherit (pkgs) lib python3Packages;
  };
  transportPackage = import ../transport/package.nix {
    inherit (pkgs) buildNpmPackage nodejs_22;
  };
  manager = pkgs.writeShellApplication {
    name = "arbor-manager";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.jq
      pkgs.util-linux
    ];
    text = builtins.readFile ../../arbor-manager/bin/arbor-manager;
  };
  registry = pkgs.writeShellScript "arbor-test-registry" ''
    install -d -m 0700 /run/arbor-test
    if [ ! -s /run/arbor-test/registry-token ]; then
      umask 077
      ${pkgs.coreutils}/bin/head -c 32 /dev/urandom | ${pkgs.coreutils}/bin/base64 -w0 > /run/arbor-test/registry-token
      printf '\n' >> /run/arbor-test/registry-token
    fi
    export ARBOR_REGISTRY_STATE_DIR=/run/arbor-test/registry-state
    export ARBOR_REGISTRY_SOCKET=/run/arbor-test/registry.sock
    export ARBOR_REGISTRY_SOCKET_TOKEN="$(cat /run/arbor-test/registry-token)"
    exec ${transportPackage}/bin/arbor-registryd
  '';
  registryReady = pkgs.writeShellScript "arbor-test-registry-ready" ''
    token=$(cat /run/arbor-test/registry-token)
    ${pkgs.python3}/bin/python - "$token" <<'PY'
    import json, socket, sys
    s = socket.socket(socket.AF_UNIX); s.settimeout(1)
    s.connect('/run/arbor-test/registry.sock')
    s.sendall((json.dumps({'operation': 'health', 'token': sys.argv[1]}) + '\n').encode())
    s.shutdown(socket.SHUT_WR)
    value = json.loads(s.recv(4096)); s.close()
    raise SystemExit(0 if value.get('ok') is True and value.get('status') == 'ok' else 1)
    PY
  '';
  openbaoStatus = pkgs.writeShellScript "arbor-test-openbao" ''
    export BAO_ADDR=http://127.0.0.1:8200
    if [ "$1" = status ]; then
      exec ${pkgs.curl}/bin/curl --silent http://127.0.0.1:8200/v1/sys/health
    fi
    exec ${pkgs.openbao}/bin/bao "$@"
  '';
  sleeper = pkgs.writeShellScript "arbor-test-sleeper" ''
    install -d -m 0700 /run/arbor-test
    if [ ! -s /run/arbor-test/registry-token ]; then
      umask 077
      ${pkgs.coreutils}/bin/head -c 32 /dev/urandom | ${pkgs.coreutils}/bin/base64 -w0 > /run/arbor-test/registry-token
      printf '\n' >> /run/arbor-test/registry-token
    fi
    export ARBOR_REGISTRY_STATE_DIR=/run/arbor-test/transport-state
    export ARBOR_REGISTRY_SOCKET=/run/arbor-test/transport.sock
    export ARBOR_REGISTRY_SOCKET_TOKEN="$(cat /run/arbor-test/registry-token)"
    exec ${transportPackage}/bin/arbor-registryd
  '';
in
pkgs.testers.nixosTest {
  name = "arbor-participant-runtime-status";
  nodes.machine =
    { ... }:
    {
      imports = [
        module
        runtimeModule
      ];
      system.stateVersion = "25.05";
      virtualisation.memorySize = 1024;
      environment.systemPackages = [
        pkgs.openbao
        pkgs.curl
        pkgs.python3
        manager
      ];

      environment.etc."arbor-test/openbao.hcl".text = ''
        storage "file" { path = "/run/arbor-test/openbao" }
        listener "tcp" { address = "127.0.0.1:8200" tls_disable = true }
        disable_mlock = true
      '';

      systemd.services.openbao-test = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "simple";
          Environment = [
            "HOME=/root"
            "BAO_ADDR=http://127.0.0.1:8200"
          ];
          ExecStart = "${pkgs.openbao}/bin/bao server -config=/etc/arbor-test/openbao.hcl";
          Restart = "on-failure";
        };
      };
      systemd.services.arbor-registry = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "simple";
          ExecStart = registry;
        };
      };
      systemd.services.arbor-registry-transport = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "simple";
          ExecStart = sleeper;
        };
      };
      systemd.services.arbor-test-vaultd = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "simple";
          ExecStart = sleeper;
        };
      };

      cluster.registry.runtime = {
        enable = true;
        registryService = "arbor-registry.service";
        transportService = "arbor-registry-transport.service";
        vaultdService = "arbor-test-vaultd.service";
        registryCommand = "${registry}";
        transportCommand = "${sleeper}";
        openbaoCommand = "${openbaoStatus}";
        registryReadyCommand = "${registryReady}";
        providerServices = [ "arbor-vault-runtime-api.service" ];
      };

      cluster.vault.runtime = {
        enable = true;
        runtimePackage = runtimePackage;
        refreshInterval = 1;
        providers.local = {
          address = "http://127.0.0.1:8200";
          authMethod = "external";
          tokenFile = "/run/arbor-test/root-token";
        };
        requirements.db = {
          provider = "local";
          path = "secret/data/arbor/db";
          field = "url";
          credentialName = "db-url";
        };
        bindings.api = {
          requirement = "db";
          service = "arbor-test-consumer";
        };
      };
      systemd.services.arbor-test-consumer = {
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${pkgs.coreutils}/bin/true";
        };
      };
    };
  testScript = ''
    import json

    def refresh():
        machine.succeed("systemctl start arbor-runtime-status.service")

    def status():
        raw = machine.succeed("cat /run/arbor/doctor/status.json")
        value = json.loads(raw)
        assert value["version"] == 1
        assert isinstance(value["healthy"], bool)
        assert isinstance(value["ready"], bool)
        assert "arbor-test" not in raw
        assert "root-token" not in raw
        return value

    def doctor(expected_status, expected_reason=None, succeeds=False):
        command = "arbor-manager doctor --format json"
        exit_code, raw = machine.execute(command)
        assert exit_code == (0 if succeeds else 1), (exit_code, raw)
        value = json.loads(raw)
        assert value["status"] == expected_status
        assert value["healthy"] is succeeds
        if expected_reason:
            assert value["reason"] == expected_reason

    start_all()
    machine.wait_for_unit("arbor-participant.target")
    machine.wait_for_unit("openbao-test.service")
    machine.wait_for_unit("arbor-registry.service")
    machine.wait_for_unit("arbor-registry-transport.service")
    machine.wait_for_unit("arbor-test-vaultd.service")
    machine.succeed("systemctl is-enabled arbor-registry.service arbor-registry-transport.service arbor-test-vaultd.service")
    machine.wait_until_succeeds("curl --fail --silent http://127.0.0.1:8080/health")
    refresh()
    value = status()
    assert value["registry"]["installed"] and value["registry"]["enabled"] and value["registry"]["running"], value
    assert value["transport"]["installed"] and value["transport"]["enabled"] and value["transport"]["running"], value
    assert value["openbao"]["installed"] and value["openbao"]["initialized"] is False, value
    assert value["provider"]["installed"] and not value["provider"]["authenticated"], value
    doctor("degraded", "OpenBao uninitialized")

    machine.succeed("install -d -m 0700 /run/arbor-test && bao operator init -key-shares=1 -key-threshold=1 -format=json >/run/arbor-test/init.json")
    machine.succeed("jq -r .root_token /run/arbor-test/init.json >/run/arbor-test/root-token && chmod 600 /run/arbor-test/root-token")
    machine.succeed("jq -r '.unseal_keys_b64[0]' /run/arbor-test/init.json >/run/arbor-test/unseal-key && chmod 600 /run/arbor-test/unseal-key")
    refresh()
    value = status()
    assert value["openbao"]["initialized"] is True and value["openbao"]["sealed"] is True
    assert not value["provider"]["authenticated"]
    doctor("degraded", "OpenBao sealed")

    machine.succeed("bao operator unseal \"$(cat /run/arbor-test/unseal-key)\"")
    machine.succeed("BAO_TOKEN=$(cat /run/arbor-test/root-token) bao kv put secret/arbor/db url=postgres://synthetic/db")
    refresh()
    value = status()
    assert value["openbao"]["initialized"] is True and value["openbao"]["sealed"] is False
    assert not value["provider"]["authenticated"]
    doctor("degraded", "provider unavailable")

    machine.succeed("systemctl reset-failed arbor-vault-runtime-api-init.service; systemctl restart arbor-vault-runtime-api-init.service")
    machine.succeed("systemctl restart arbor-vault-runtime-api.service")
    machine.wait_for_unit("arbor-vault-runtime-api.service")
    refresh()
    value = status()
    assert value["provider"]["running"] and value["provider"]["authenticated"]
    doctor("healthy", succeeds=True)

    machine.succeed("rm -f /run/arbor-vaultd/ready/api")
    refresh()
    value = status()
    assert not value["provider"]["authenticated"]
    doctor("degraded", "provider unavailable")
    machine.succeed("systemctl restart arbor-vault-runtime-api.service")
    machine.wait_for_unit("arbor-vault-runtime-api.service")

    machine.succeed("systemctl stop arbor-registry.service")
    refresh()
    value = status()
    assert value["registry"]["installed"] and value["registry"]["enabled"] and not value["registry"]["running"]
    assert not value["registry"]["ready"]
    doctor("degraded", "registry unavailable")
    machine.succeed("systemctl start arbor-registry.service")
    machine.wait_for_unit("arbor-registry.service")
    refresh()
    value = status()
    assert value["registry"]["ready"] and value["ready"]
    doctor("healthy", succeeds=True)
  '';
}
