{ config, lib, ... }:
let
  externalFileModule =
    { ... }:
    {
      options = {
        path = lib.mkOption {
          type = lib.types.strMatching "/.*";
          description = "Absolute runtime path; file contents never enter Nix evaluation.";
        };
        owner = lib.mkOption {
          type = lib.types.str;
          default = "root";
          description = "Expected runtime owner of the external file.";
        };
        group = lib.mkOption {
          type = lib.types.str;
          default = "root";
          description = "Expected runtime group of the external file.";
        };
        mode = lib.mkOption {
          type = lib.types.strMatching "[0-7]{4}";
          default = "0400";
          description = "Expected mode; secret files default to owner-read-only.";
        };
        neededForUsers = lib.mkOption {
          type = lib.types.bool;
          default = false;
          description = "Whether the file must be available before users are created.";
        };
      };
    };
in
{
  options.arbor.environment = {
    externalFiles = {
      root = lib.mkOption {
        type = lib.types.strMatching "/.*";
        default = "/etc/nix-arbor";
        description = "Public root convention for operator-provisioned files.";
      };
      files = lib.mkOption {
        type = lib.types.attrsOf (lib.types.submodule externalFileModule);
        default = {
          r640SopsFile = {
            path = "/etc/nix-arbor/r640-0.sops.yaml";
          };
          hostAgeKey = {
            path = "/var/lib/host-age/keys.txt";
          };
          ashPasswordHash = {
            path = "/run/secrets/ash-password";
            neededForUsers = true;
          };
          madelinePasswordHash = {
            path = "/run/secrets/madeline-password";
            neededForUsers = true;
          };
          desktoptoodleSshIdentity = {
            path = "/home/ash/.ssh/desktoptoodle";
            owner = "ash";
            group = "users";
          };
          r640SshIdentity = {
            path = "/root/.ssh/r640-0";
          };
        };
        description = "Provider-independent references to operator-provisioned files; never file contents.";
      };
    };
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
        options = {
          enable = lib.mkOption {
            type = lib.types.bool;
            default = false;
          };
          provider = lib.mkOption {
            type = lib.types.enum [
              "sops"
              "external-files"
            ];
            default = "sops";
          };
        };
      };
      default = { };
      description = "Optional account secret provider configuration.";
    };
  };
}
