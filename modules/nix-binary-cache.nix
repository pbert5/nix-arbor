{ inputs, ... }:
{
  # Export separately from machine profiles so integration must opt in
  # explicitly. The underlying Attic module is pinned by flake.lock.
  flake.nixosModules.arbor-nix-binary-cache = {
    imports = [
      (inputs.attic + "/nixos/atticd.nix")
      ../config/modules/nix-binary-cache.nix
    ];
  };
}
