{ lib, ... }:
{
  options.arbor.access.authorizedKeySets = lib.mkOption {
    type = lib.types.listOf (
      lib.types.enum [
        "operator"
        "deployment"
      ]
    );
    default = [ "operator" ];
    description = "Named public SSH key sets explicitly enabled on this machine.";
  };
}
