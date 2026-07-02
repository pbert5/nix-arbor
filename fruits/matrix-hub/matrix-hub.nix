{
  hostInventory,
  lib,
  pkgs,
  site,
  ...
}:
let
  matrixOrg = lib.attrByPath [ "org" "matrixHub" ] { } hostInventory;
  endpoint = site.ports.matrixContinuwuity;
  bootstrapDir = "/var/lib/matrix-hub-bootstrap";
in
{
  services.matrix-continuwuity = {
    enable = true;
    settings.global = {
      server_name = matrixOrg.serverName or "matrix.internal";
      address = [ endpoint.bind ];
      port = [ endpoint.port ];
      allow_federation = false;
      allow_registration = false;
    };
  };

  networking.firewall.interfaces.${endpoint.firewallInterface}.allowedTCPPorts = [
    endpoint.port
  ];

  # Registers a Matrix admin account on first boot and stores the generated
  # password in ${bootstrapDir}/admin-password (root:root 600).
  # Retrieve with: ssh r640-0 cat ${bootstrapDir}/admin-password
  # Skips silently once ${bootstrapDir}/done exists.
  systemd.services.matrix-hub-bootstrap = {
    description = "Matrix Hub first-admin bootstrap";
    after = [
      "continuwuity.service"
      "network.target"
    ];
    wants = [ "continuwuity.service" ];
    wantedBy = [ "multi-user.target" ];
    unitConfig.ConditionPathExists = "!${bootstrapDir}/done";
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [
      pkgs.curl
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.gawk
      pkgs.openssl
      pkgs.jq
      pkgs.systemd
    ];
    script = ''
      set -euo pipefail

      SERVER="http://localhost:${toString endpoint.port}"

      install -d -m 0700 "${bootstrapDir}"

      # Wait for the HTTP endpoint (up to 60 s)
      for i in $(seq 1 30); do
        curl -sf "$SERVER/_matrix/client/versions" > /dev/null && break
        if [ "$i" -eq 30 ]; then
          echo "continuwuity not ready after 60 s" >&2
          exit 1
        fi
        sleep 2
      done

      # Extract the one-time registration token Continuwuity logs at first start
      TOKEN=$(journalctl -u continuwuity --no-pager -l \
        | grep -o 'registration token [A-Za-z0-9_-]*' \
        | awk '{print $NF}' | tail -1)
      if [ -z "$TOKEN" ]; then
        echo "No registration token found in journal" >&2
        exit 1
      fi

      # Generate a random password
      PASSWORD=$(openssl rand -base64 24 | tr -d '/+=\n')

      # UIAA step 1: probe registration to get session ID (server returns 401)
      PROBE=$(curl -s -X POST "$SERVER/_matrix/client/v3/register" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"admin\",\"password\":\"$PASSWORD\",\"kind\":\"user\"}")
      SESSION=$(echo "$PROBE" | jq -r '.session')
      if [ -z "$SESSION" ] || [ "$SESSION" = "null" ]; then
        echo "No UIAA session returned: $PROBE" >&2
        exit 1
      fi

      # UIAA step 2: complete registration with the token
      RESULT=$(curl -sf -X POST "$SERVER/_matrix/client/v3/register" \
        -H 'Content-Type: application/json' \
        -d "{\"username\":\"admin\",\"password\":\"$PASSWORD\",\"kind\":\"user\",\"auth\":{\"type\":\"m.login.registration_token\",\"token\":\"$TOKEN\",\"session\":\"$SESSION\"}}")
      USER_ID=$(echo "$RESULT" | jq -r '.user_id')
      if [ -z "$USER_ID" ] || [ "$USER_ID" = "null" ]; then
        echo "Registration failed: $RESULT" >&2
        exit 1
      fi

      echo "Registered Matrix admin: $USER_ID"

      # Persist the password and mark bootstrap complete
      umask 077
      echo "$PASSWORD" > "${bootstrapDir}/admin-password"
      touch "${bootstrapDir}/done"
      echo "Bootstrap complete. Password at ${bootstrapDir}/admin-password"
    '';
  };
}
