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
  mkdir -p fakebin
  cat > fakebin/openssl <<'EOF'
  #!/bin/sh
  set -eu
  case "$*" in
    *"-fingerprint -sha256"*)
      printf '%s\n' 'sha256 Fingerprint=D7:A7:A0:FB:5D:7E:27:31:D7:71:E9:48:4E:BC:DE:F7:1D:5F:0C:3E:0A:29:48:78:2B:C8:3E:E0:EA:69:9E:F4'
      printf '%s\n' fingerprint >> "$FAKE_OPENSSL_CALLS"
      ;;
    *"-text"*)
      test -r "$OPENSSL_TEXT_FIXTURE"
      cat "$OPENSSL_TEXT_FIXTURE"
      printf '%s\n' text >> "$FAKE_OPENSSL_CALLS"
      ;;
    *)
      exit 2
      ;;
  esac
  EOF
  chmod +x fakebin/openssl
  check_ca_guard_rejects() {
    fixture="$1"
    message="$2"
    : > fakebin/calls
    if PATH="$PWD/fakebin:$PATH" FAKE_OPENSSL_CALLS="$PWD/fakebin/calls" OPENSSL_TEXT_FIXTURE="$fixture" bash ${./check-ca-bundle.sh} ${../tests/fixtures/old-comodo-aaa.pem}; then
      echo "$message" >&2
      exit 1
    fi
    if ! grep -Fxq fingerprint fakebin/calls; then
      echo "Fake OpenSSL fingerprint response was not exercised" >&2
      exit 1
    fi
    if ! grep -Fxq text fakebin/calls; then
      echo "Fake OpenSSL text response was not exercised" >&2
      exit 1
    fi
  }
  check_ca_guard_rejects ${../tests/fixtures/openssl-output-alias.txt} "CA guard accepted alias metadata for a missing rejection purpose"
  check_ca_guard_rejects ${../tests/fixtures/openssl-output-injected.txt} "CA guard accepted an alias-injected trust/rejection block"
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
