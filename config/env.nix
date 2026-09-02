{ config, lib, ... }:
{
  options.arbor.environment = {
    public = lib.mkOption {
      type = lib.types.submodule {
        options = {
          sshHosts = lib.mkOption {
            type = lib.types.attrsOf lib.types.attrs;
            default = { };
          };
          resources = lib.mkOption {
            type = lib.types.attrsOf lib.types.str;
            default = { };
          };
        };
      };
      default = {
        resources = {
          zfsRoot = "/mypool";
          ashHome = "/home/ash";
          madelineHome = "/home/madeline";
        };
        sshHosts = {
          # Transitional static endpoint catalog.  These addresses are the
          # current Tailscale/underlay endpoints recorded by the legacy
          # bootstrap inventory; Registry endpoint records can replace this
          # projection later without changing the aliases.
          evolver = {
            hostname = "100.97.84.12";
            user = "ash";
            identityFile = "/home/ash/.ssh/arbor-r640-evolver-deployer";
            identitiesOnly = true;
            identityAgent = "$SSH_AUTH_SOCK";
            addKeysToAgent = "no";
            forwardAgent = false;
          };
          root-evolver = {
            hostname = "100.97.84.12";
            user = "root";
            identityFile = "/home/ash/.ssh/arbor-r640-evolver-deployer";
            identitiesOnly = true;
            identityAgent = "$SSH_AUTH_SOCK";
            addKeysToAgent = "no";
            forwardAgent = false;
          };
          desktoptoodle = {
            hostname = "100.112.11.124";
            user = "ash";
            identityFile = "/home/ash/.ssh/r640-0";
            identitiesOnly = true;
            identityAgent = "$SSH_AUTH_SOCK";
            addKeysToAgent = "no";
            forwardAgent = false;
          };
          r640-0 = {
            hostname = "100.110.27.100";
            user = "ash";
            identityFile = "/home/ash/.ssh/cluster-leader-ed25519";
            identitiesOnly = true;
            identityAgent = "$SSH_AUTH_SOCK";
            addKeysToAgent = "no";
            forwardAgent = false;
          };
          bal-lab = {
            hostname = "bal-lab.glbrc.org";
            user = "psilbert";
            identityFile = "/home/ash/.ssh/bal-lab-glbrc-ed25519";
            identitiesOnly = true;
            identityAgent = "$SSH_AUTH_SOCK";
            addKeysToAgent = "no";
            forwardAgent = false;
          };
        };
      };
      description = "Transitional public registry fallback; dynamic runtime data may replace it later.";
    };
    secrets = lib.mkOption {
      type = lib.types.submodule {
        options.enable = lib.mkOption {
          type = lib.types.bool;
          default = false;
        };
      };
      default = { };
      description = "Optional encrypted SOPS file provisioned by the operator.";
    };
  };
  config = lib.mkIf config.arbor.environment.secrets.enable {
    sops.defaultSopsFile = "/etc/nix-arbor/r640-0.sops.yaml";
    sops.age.keyFile = "/var/lib/host-age/keys.txt";
    sops.secrets.ash-password = {
      key = "ash_password_hash";
      neededForUsers = true;
      owner = "root";
      mode = "0400";
    };
    sops.secrets.madeline-password = {
      key = "madeline_password_hash";
      neededForUsers = true;
      owner = "root";
      mode = "0400";
    };
  };
}
