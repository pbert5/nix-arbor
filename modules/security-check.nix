{
  config,
  lib,
  pkgs,
}:
let
  machines = config.flake.nixosConfigurations;
  patchedNix =
    version:
    (lib.hasPrefix "2.34." version && lib.versionAtLeast version "2.34.9")
    || (lib.hasPrefix "2.35." version && lib.versionAtLeast version "2.35.3");
  bundles = lib.mapAttrsToList (_: machine: machine.config.security.pki.caBundle) machines;
in
assert !patchedNix "2.34.8";
assert !patchedNix "2.35.2";
assert !patchedNix "2.36.0";
assert patchedNix "2.34.9";
assert patchedNix "2.35.3";
assert lib.all (machine: patchedNix machine.config.nix.package.version) (
  builtins.attrValues machines
);
pkgs.runCommand "nix-arbor-host-security" { nativeBuildInputs = [ pkgs.openssl ]; } ''
  if bash ${./check-ca-bundle.sh} ${../tests/fixtures/old-comodo-aaa.pem}; then
    echo "Old trusted CA fixture was not rejected" >&2
    exit 1
  fi
  for bundle in ${lib.escapeShellArgs bundles}; do
    bash ${./check-ca-bundle.sh} "$bundle"
  done
  touch "$out"
''
