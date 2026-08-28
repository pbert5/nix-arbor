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
        sshHosts = { };
      };
      description = "Transitional public registry fallback; dynamic runtime data may replace it later.";
    };
  };
}
