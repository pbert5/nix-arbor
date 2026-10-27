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
  for fixture in ${../tests/fixtures/old-comodo-aaa.pem} ${../tests/fixtures/old-emsign-c3.pem} ${../tests/fixtures/old-emsign-g3.pem} ${../tests/fixtures/old-emsign-c1.pem}; do
    if bash ${./check-ca-bundle.sh} "$fixture"; then
      echo "Old trusted CA fixture was not rejected: $fixture" >&2
      exit 1
    fi
  done
  openssl verify -purpose smimesign -CAfile ${../tests/fixtures/old-comodo-aaa.pem} ${../tests/fixtures/old-comodo-aaa.pem}
  for bundle in ${lib.escapeShellArgs bundles}; do
    bash ${./check-ca-bundle.sh} "$bundle"
    if openssl verify -purpose smimesign -CAfile "$bundle" ${../tests/fixtures/old-comodo-aaa.pem}; then
      echo "Affected root remains trusted for S/MIME in $bundle" >&2
      exit 1
    fi
  done
  touch "$out"
''
