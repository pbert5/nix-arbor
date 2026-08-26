{
  module,
  pkgs,
  upstreamModules,
}:
let
  runtimePackage = import ../runtime/package.nix {
    inherit (pkgs) lib python3Packages;
  };
  openbaoServer = pkgs.writeShellScript "arbor-openbao-autoauth-server" ''
    set -eu
    install -d -m 0700 /run/arbor-test
    root_token=$(head -c 32 /dev/urandom | ${pkgs.coreutils}/bin/base64 -w0)
    printf '%s\n' "$root_token" >/run/arbor-test/root-token
    chmod 0600 /run/arbor-test/root-token
    exec ${pkgs.openbao}/bin/bao server -dev \
      -dev-root-token-id="$root_token" \
      -dev-listen-address=0.0.0.0:8200
  '';
in
pkgs.testers.nixosTest {
  name = "arbor-registry-vault-agent-autoauth";
  nodes.machine =
    {
      ...
    }:
    {
      imports = upstreamModules ++ [ module ];
      system.stateVersion = "25.05";
      virtualisation.memorySize = 1024;

      systemd.services.openbao-test = {
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "simple";
          Environment = [
            "HOME=/root"
            "PATH=${pkgs.bash}/bin:${pkgs.coreutils}/bin:${pkgs.openbao}/bin"
          ];
          ExecStart = openbaoServer;
          Restart = "on-failure";
          StandardOutput = "null";
          StandardError = "null";
        };
      };

      systemd.services.seed-openbao-autoauth = {
        wantedBy = [ "multi-user.target" ];
        after = [ "openbao-test.service" ];
        requires = [ "openbao-test.service" ];
        before = [ "vault-agent-default.service" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          set -eu
          for attempt in $(seq 1 100); do
            if ${pkgs.curl}/bin/curl --fail --silent http://127.0.0.1:8200/v1/sys/health >/dev/null; then
              break
            fi
            sleep 0.1
          done
          ${pkgs.curl}/bin/curl --fail --silent http://127.0.0.1:8200/v1/sys/health >/dev/null
          install -d -m 0700 /run/arbor-test
          root_token=$(cat /run/arbor-test/root-token)
          printf '%s\n' 'path "secret/data/arbor/*" { capabilities = [ "read" ] }' >/run/arbor-test/policy
          BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN="$root_token" \
            ${pkgs.openbao}/bin/bao policy write arbor-autoauth /run/arbor-test/policy >/dev/null
          BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN="$root_token" \
            ${pkgs.openbao}/bin/bao auth enable approle >/dev/null
          BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN="$root_token" \
            ${pkgs.openbao}/bin/bao write auth/approle/role/arbor-autoauth \
            token_policies=arbor-autoauth >/dev/null
          BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN="$root_token" \
            ${pkgs.openbao}/bin/bao read -field=role_id auth/approle/role/arbor-autoauth/role-id \
            >/run/arbor-test/role-id
          BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN="$root_token" \
            ${pkgs.openbao}/bin/bao write -field=secret_id -f auth/approle/role/arbor-autoauth/secret-id \
            >/run/arbor-test/secret-id
          chmod 0600 /run/arbor-test/role-id /run/arbor-test/secret-id
          secret_v1=$(head -c 24 /dev/urandom | ${pkgs.coreutils}/bin/base64 -w0)
          printf '%s\n' "$secret_v1" >/run/arbor-test/expected-v1
          chmod 0600 /run/arbor-test/expected-v1
          BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN="$root_token" \
            ${pkgs.openbao}/bin/bao kv put secret/arbor/db url="$secret_v1" >/dev/null
        '';
      };

      systemd.services.rotate-openbao-autoauth = {
        serviceConfig = {
          Type = "oneshot";
          ExecStart = pkgs.writeShellScript "arbor-openbao-autoauth-rotate" ''
            set -eu
            root_token=$(cat /run/arbor-test/root-token)
            secret=$(head -c 24 /dev/urandom | ${pkgs.coreutils}/bin/base64 -w0)
            printf '%s\n' "$secret" >/run/arbor-test/expected-next
            chmod 0600 /run/arbor-test/expected-next
            BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN="$root_token" \
              ${pkgs.openbao}/bin/bao kv put secret/arbor/db url="$secret" >/dev/null
          '';
        };
      };

      systemd.services.vault-agent-default = {
        after = [ "seed-openbao-autoauth.service" ];
        requires = [ "seed-openbao-autoauth.service" ];
      };

      systemd.services.arbor-vault-runtime-api-db-init = {
        after = [ "vault-agent-default.service" ];
        requires = [ "vault-agent-default.service" ];
      };

      systemd.services.api = {
        wantedBy = [ "multi-user.target" ];
        script = ''
          set -eu
          trap 'touch /run/FAILED-VAULT-CONSUMER-ROTATION' ERR
          value=$(cat "$CREDENTIALS_DIRECTORY/db-url")
          test -n "$value"
          printf '%s\n' "$value" >/run/api-credential
          date +%s%N >/run/api-started
        '';
      };

      services.vault.agents.default.settings = {
        vault.address = "http://127.0.0.1:8200";
        auto_auth = {
          method = [
            {
              type = "approle";
              config = {
                role_id_file_path = "/run/arbor-test/role-id";
                secret_id_file_path = "/run/arbor-test/secret-id";
                remove_secret_id_file_after_reading = false;
              };
            }
          ];
          sink = [
            {
              type = "file";
              config.path = "/run/arbor-test/agent-token";
            }
          ];
        };
      };

      cluster.vault.runtime = {
        enable = true;
        useUpstreamVaultd = true;
        useProviderBridge = true;
        runtimePackage = runtimePackage;
        refreshInterval = 1;
        providers.local = {
          address = "http://127.0.0.1:8200";
          authMethod = "external";
          tokenFile = "/run/arbor-test/agent-token";
        };
        requirements.db = {
          provider = "local";
          path = "secret/data/arbor/db";
          field = "url";
          credentialName = "db-url";
        };
        bindings.api = {
          requirement = "db";
          service = "api";
        };
      };
    };
  testScript = ''
    start_all()
    machine.wait_for_unit("seed-openbao-autoauth.service")
    machine.wait_for_unit("vault-agent-default.service")
    machine.wait_until_succeeds("test -s /run/arbor-test/agent-token")
    machine.wait_for_unit("arbor-vault-runtime-api-bridge.service")
    machine.wait_for_unit("api.service")
    machine.succeed("test \"$(cat /run/api-credential)\" = \"$(cat /run/arbor-test/expected-v1)\"")
    machine.succeed("test \"$(stat -c %a /run/arbor-test/agent-token)\" = 600")
    machine.succeed("test \"$(stat -c %a /run/systemd-vaultd/secrets/api.service.json)\" = 400")
    machine.succeed("test ! -e /run/FAILED-VAULT-CONSUMER-ROTATION")
    first_start = machine.succeed("cat /run/api-started").strip()

    machine.succeed("systemctl start rotate-openbao-autoauth.service")
    machine.wait_until_succeeds("test \"$(cat /run/api-credential)\" = \"$(cat /run/arbor-test/expected-next)\"")
    second_start = machine.succeed("cat /run/api-started").strip()
    assert second_start != first_start
    machine.succeed("test ! -e /run/FAILED-VAULT-CONSUMER-ROTATION")

    machine.succeed("systemctl stop vault-agent-default.service")
    machine.succeed("rm -f /run/arbor-test/agent-token")
    machine.succeed("systemctl start vault-agent-default.service")
    machine.wait_until_succeeds("test -s /run/arbor-test/agent-token")
    machine.succeed("systemctl start rotate-openbao-autoauth.service")
    machine.wait_until_succeeds("test \"$(cat /run/api-credential)\" = \"$(cat /run/arbor-test/expected-next)\"")
    machine.succeed("test ! -e /run/FAILED-VAULT-CONSUMER-ROTATION")
  '';
}
