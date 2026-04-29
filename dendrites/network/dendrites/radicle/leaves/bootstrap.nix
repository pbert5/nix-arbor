{ lib, pkgs, hostInventory, hostName, ... }:
let
  radicleOrg = lib.attrByPath [ "org" "network" "radicle" ] { } hostInventory;
  privateKeyFile = radicleOrg.privateKeyFile or null;
  serviceEnabled = privateKeyFile != null;
  radHome = "/var/lib/radicle";
in
{
  # Initialise the Radicle identity on first boot if the key doesn't exist yet.
  # rad auth creates the key at $RAD_HOME/keys/radicle AND writes config.json.
  # To re-key: stop radicle-seed, delete $radHome/keys/radicle, reboot.
  systemd.services.radicle-keygen = lib.mkIf serviceEnabled {
    description = "Initialise Radicle node identity (first boot)";
    wantedBy = [ "multi-user.target" ];
    before = [ "radicle-seed.service" ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      User = "radicle";
      Group = "radicle";
    };
    environment = {
      RAD_HOME = radHome;
      # Empty passphrase for unattended first-boot key generation.
      # The key is protected at rest by filesystem permissions (0700 dir, 0600 file).
      RAD_PASSPHRASE = "";
    };
    script = ''
      set -euo pipefail
      if [ ! -f "${radHome}/config.json" ]; then
        mkdir -p "${radHome}"
        chmod 700 "${radHome}"
        # Remove any pre-existing bare SSH key (created by old bootstrap or manual ssh-keygen).
        # rad auth must own the key so it can set up the full identity.
        rm -f "${radHome}/keys/radicle" "${radHome}/keys/radicle.pub"
        echo "Initialising Radicle identity for ${hostName}..."
        ${lib.getExe' pkgs.radicle-node "rad"} auth --alias "${hostName}"
        echo "Radicle identity initialised."
      fi
    '';
  };

  systemd.tmpfiles.rules = lib.mkIf serviceEnabled [
    "d ${radHome} 0700 radicle radicle - -"
  ];
}
