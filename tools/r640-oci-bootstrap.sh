#!/usr/bin/env bash
# R640-0 private OCI registry bootstrap. Use: bash tools/r640-oci-bootstrap.sh
# Run as the normal operator user; local sudo prompts are expected.
# This activates ONLY the registry, not CI runners or the optional Nix cache.
set -Eeuo pipefail
umask 077

BASE=9a64d54c72eb3d97c72f00663f3ab017a71ef64d
BRANCH=agent/ci/r640-oci-bootstrap
HOST=r640-0.tenrec-bearded.ts.net
STORE=/var/lib/arbor-secrets/private-oci-registry
ROOT="$(cd "$(dirname "$0")/.." && pwd -P)"
PREVIOUS="$(readlink -f /run/current-system)"
TMP=""

fail() { echo "ERROR: $*" >&2; exit 1; }
cleanup() {
  if [[ -n "$TMP" && -d "$TMP" ]]; then rm -rf -- "$TMP"; fi
}
on_error() {
  rc=$?
  echo "BOOTSTRAP FAILED (exit $rc)." >&2
  echo "Original running closure: $PREVIOUS" >&2
  echo "If activation changed services, investigate, then restore if appropriate:" >&2
  echo "  sudo $PREVIOUS/bin/switch-to-configuration test" >&2
  exit "$rc"
}
trap cleanup EXIT
trap on_error ERR

[[ "$(id -u)" != 0 ]] || fail "Run as your regular operator account, not root."
[[ "$(hostname -s)" == r640-0 ]] || fail "This tool must run on r640-0."
[[ "$(git -C "$ROOT" branch --show-current)" == "$BRANCH" ]] || fail "Checkout $BRANCH before running."
git -C "$ROOT" merge-base --is-ancestor "$BASE" HEAD || fail "Reviewed integration base is missing."
git -C "$ROOT" diff --quiet && git -C "$ROOT" diff --cached --quiet || fail "Tracked files contain uncommitted changes."
mountpoint -q /mypool || fail "/mypool is not mounted."
zpool status -x mypool | grep -q 'is healthy' || fail "mypool reports a problem."
for unit in sshd tailscaled docker; do
  systemctl is-active --quiet "$unit" || fail "$unit is inactive."
done
docker info >/dev/null || fail "Current user cannot access Docker."
[[ -x "$PREVIOUS/bin/switch-to-configuration" ]] || fail "Cannot find running-system recovery tool."
BOOTED="$(readlink -f /run/booted-system)"
[[ -x "$BOOTED/bin/switch-to-configuration" ]] || fail "Cannot find booted-system recovery tool."
DNS="$(tailscale status --json | jq -r '.Self.DNSName | rtrimstr(".")')"
[[ "$DNS" == "$HOST" ]] || fail "Expected tailnet DNS $HOST, found $DNS."
SERVE="$(tailscale serve status)"
if [[ "$SERVE" != *"No serve config"* ]]; then
  fail "Existing Tailscale Serve config: inspect ports 443/8443 manually before proceeding."
fi

# Validate both the safe default and the explicitly opted-in NixOS outputs.
[[ "$(nix eval --json "$ROOT#nixosConfigurations.r640-0.config.arbor.ci.privateRegistry.enable")" == false ]] \
  || fail "Default r640-0 registry must remain disabled."
[[ "$(nix eval --json "$ROOT#nixosConfigurations.r640-0-oci.config.arbor.ci.privateRegistry.enable")" == true ]] \
  || fail "The r640-0-oci registry is not enabled."
[[ "$(nix eval --json "$ROOT#nixosConfigurations.r640-0-oci.config.arbor.ci.runners.enable")" == false ]] \
  || fail "Runner VMs must remain disabled."
[[ "$(nix eval --json "$ROOT#nixosConfigurations.r640-0-oci.config.arbor.environment.secrets.enable")" == false ]] \
  || fail "Unexpected legacy SOPS secret-mode activation."

echo "Using branch $BRANCH at $(git -C "$ROOT" rev-parse HEAD)"
echo "Running system: $PREVIOUS"
echo "Booted system:  $BOOTED"
echo "Validating sudo and preserving recovery closures..."
sudo -v
sudo install -d -m 0755 /nix/var/nix/gcroots/arbor-oci-recovery
sudo ln -sfn -- "$PREVIOUS" /nix/var/nix/gcroots/arbor-oci-recovery/before-registry-running
sudo ln -sfn -- "$BOOTED" /nix/var/nix/gcroots/arbor-oci-recovery/before-registry-booted

# Use the flake's pinned Apache htpasswd, not a host-provided unknown version.
HTROOT="$(nix build --no-link --print-out-paths \
  "$ROOT#nixosConfigurations.r640-0-oci.pkgs.apacheHttpd" | tail -n 1)"
[[ -x "$HTROOT/bin/htpasswd" ]] || fail "htpasswd executable unavailable."

# Persist secrets outside Git and Nix; /run auth copies are staged by systemd.
# If only some prior files exist, stop rather than accidentally rotate a password.
sudo bash -s -- "$STORE" "$HTROOT/bin/htpasswd" <<'ROOT_SETUP'
set -Eeuo pipefail
umask 077
store="$1"
htpasswd="$2"
install -d -m 0700 -o root -g root "$store"
n=0
for f in pull.password push.password pull.htpasswd push.htpasswd; do
  if test -s "$store/$f"; then n=$((n + 1)); fi
done
if [ "$n" -ne 0 ] && [ "$n" -ne 4 ]; then
  echo "Partial credential provisioning: inspect root-only store before rerunning." >&2
  exit 1
fi
if [ "$n" -eq 0 ]; then
  od -An -tx1 -N32 /dev/urandom | tr -d ' \n' > "$store/pull.password"
  od -An -tx1 -N32 /dev/urandom | tr -d ' \n' > "$store/push.password"
  "$htpasswd" -iB -c "$store/pull.htpasswd" r640pull < "$store/pull.password"
  "$htpasswd" -iB -c "$store/push.htpasswd" r640push < "$store/push.password"
fi
for f in pull.password push.password pull.htpasswd push.htpasswd; do
  test -s "$store/$f"
  chown root:root "$store/$f"
  chmod 0600 "$store/$f"
done
ROOT_SETUP

echo "Building focused isolation and registry checks..."
nix build --no-link \
  "$ROOT#checks.x86_64-linux.ci-runner-isolation" \
  "$ROOT#checks.x86_64-linux.private-oci-registry"

echo "Reviewing the activation preview..."
sudo nixos-rebuild dry-activate --flake "$ROOT#r640-0-oci"
echo "Activating the registry for a reversible live trial..."
sudo nixos-rebuild test --flake "$ROOT#r640-0-oci"

# The auth staging service copies files into the nginx-owned runtime directory.
sudo systemctl start arbor-oci-auth.service
sudo systemctl restart docker-registry.service
sudo systemctl restart nginx.service
sudo systemctl restart tailscale-oci-registry-serve.service
for unit in sshd tailscaled docker docker-registry nginx tailscale-oci-registry-serve; do
  systemctl is-active --quiet "$unit" || fail "$unit is inactive after activation."
done
mountpoint -q /mypool || fail "/mypool disappeared after activation."

TMP="$(mktemp -d)"
chmod 0700 "$TMP"
anon="$(curl -sS --max-time 25 -o /dev/null -w '%{http_code}' "https://$HOST/v2/")"
[[ "$anon" == 401 ]] || fail "Anonymous GET /v2/: expected 401, received $anon."

# Curl config and Docker credential stores are restricted to this temp folder.
# Passwords are not passed on the command line or printed in the logs.
printf 'user = "r640pull:%s"\n' "$(sudo cat "$STORE/pull.password")" > "$TMP/reader.curl"
chmod 0600 "$TMP/reader.curl"
reader="$(curl -sS --max-time 25 --config "$TMP/reader.curl" -o /dev/null -w '%{http_code}' "https://$HOST/v2/")"
[[ "$reader" == 200 ]] || fail "Reader GET /v2/: expected 200, received $reader."
denied="$(curl -sS --max-time 25 --config "$TMP/reader.curl" -X POST -o /dev/null -w '%{http_code}' \
  "https://$HOST/v2/ci/r640-smoke/blobs/uploads/")"
[[ "$denied" == 403 || "$denied" == 405 ]] || fail "Reader write was not denied (HTTP $denied)."

mkdir -m 0700 "$TMP/writer-docker" "$TMP/reader-docker" "$TMP/context"
sudo cat "$STORE/push.password" | docker --config "$TMP/writer-docker" login \
  --username r640push --password-stdin "$HOST:8443"
sudo cat "$STORE/pull.password" | docker --config "$TMP/reader-docker" login \
  --username r640pull --password-stdin "$HOST"

printf 'R640 OCI acceptance at %s\n' "$(git -C "$ROOT" rev-parse HEAD)" > "$TMP/context/hello.txt"
printf 'FROM scratch\nCOPY hello.txt /hello.txt\n' > "$TMP/context/Dockerfile"
SHA="$(git -C "$ROOT" rev-parse HEAD)"
IMAGE="$HOST:8443/ci/r640-smoke:$SHA"
docker build -t "$IMAGE" "$TMP/context"
docker --config "$TMP/writer-docker" push "$IMAGE" | tee "$TMP/push.log"
DIGEST="$(sed -n 's/.*digest: \(sha256:[[:xdigit:]]*\).*/\1/p' "$TMP/push.log" | tail -n 1)"
[[ "$DIGEST" =~ ^sha256:[[:xdigit:]]{64}$ ]] || fail "No complete SHA256 digest found in push output."
docker --config "$TMP/reader-docker" pull "$HOST/ci/r640-smoke@$DIGEST"

echo "Registry authentication, image push and digest pull passed."
echo "Making the accepted system the boot default..."
sudo nixos-rebuild switch --flake "$ROOT#r640-0-oci"
for unit in sshd tailscaled docker docker-registry nginx tailscale-oci-registry-serve; do
  systemctl is-active --quiet "$unit" || fail "$unit inactive after switch."
done

echo "SUCCESS: reader https://$HOST (443); writer https://$HOST:8443"
echo "SUCCESS: ci/r640-smoke@$DIGEST"
echo "Root-only credential directory: $STORE"
echo "Recovery: sudo $PREVIOUS/bin/switch-to-configuration test"
echo "Important: restrict access to tailnet ports 443/8443 in Tailscale ACLs."
echo "CI runner VMs and optional Nix binary cache remain disabled."
echo "R640_CI_READY remains unset pending runner and full end-to-end acceptance."
