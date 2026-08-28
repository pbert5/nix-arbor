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
        sshHosts = { };
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
