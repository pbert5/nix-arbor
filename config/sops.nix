{ config, lib, ... }:
{
  options.arbor.environment.secrets.enable = lib.mkOption {
    type = lib.types.bool;
    default = false;
    description = "Enable the optional SOPS provider for external files.";
  };

  config = lib.mkIf config.arbor.environment.secrets.enable {
    sops.defaultSopsFile = config.arbor.environment.externalFiles.files.r640SopsFile.path;
    sops.age.keyFile = config.arbor.environment.externalFiles.files.hostAgeKey.path;
    sops.secrets.ash-password = {
      key = "ash_password_hash";
      neededForUsers = true;
      path = config.arbor.environment.externalFiles.files.ashPasswordHash.path;
      owner = config.arbor.environment.externalFiles.files.ashPasswordHash.owner;
      group = config.arbor.environment.externalFiles.files.ashPasswordHash.group;
      mode = config.arbor.environment.externalFiles.files.ashPasswordHash.mode;
    };
    sops.secrets.madeline-password = {
      key = "madeline_password_hash";
      neededForUsers = true;
      path = config.arbor.environment.externalFiles.files.madelinePasswordHash.path;
      owner = config.arbor.environment.externalFiles.files.madelinePasswordHash.owner;
      group = config.arbor.environment.externalFiles.files.madelinePasswordHash.group;
      mode = config.arbor.environment.externalFiles.files.madelinePasswordHash.mode;
    };
  };
}
