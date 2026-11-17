#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/bootstrap" "$tmp/run"
sed -e "s|/var/lib/raspberry-evolver/bootstrap/tailscale.authkey|$tmp/bootstrap/tailscale.authkey|" -e "s|/run/raspberry-evolver/bootstrap.status|$tmp/run/bootstrap.status|" "$repo/config/machines/raspberry-evolver/bootstrap.sh" > "$tmp/bootstrap.sh"
cat > "$tmp/bin/tailscale" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$TEST_DIR/argv"
if [ "$1" = switch ]; then [ ! -e "$TEST_DIR/profile-error" ] || exit 1; cat "$TEST_DIR/profiles"; exit; fi
if [ "$1" = debug ]; then cat "$TEST_DIR/prefs"; exit; fi
if [ -e "$TEST_DIR/offline" ]; then exit 1; fi
if [ "$1" = up ]; then
  if [ -f "$TEST_DIR/after-up" ]; then cp "$TEST_DIR/after-up" "$TEST_DIR/state"; fi
  exit 1
fi
cat "$TEST_DIR/state"
MOCK
chmod +x "$tmp/bin/tailscale"
export TEST_DIR=$tmp PATH="$tmp/bin:$PATH"
key=$tmp/bootstrap/tailscale.authkey
status=$tmp/run/bootstrap.status
run() { bash "$tmp/bootstrap.sh" >"$tmp/output" 2>&1; }
needs='{"BackendState":"NeedsLogin"}'
enrolled='{"BackendState":"Running","Self":{"Online":true,"TailscaleIPs":["100.1.2.3"]}}'
pending='{"BackendState":"NeedsMachineAuth"}'
printf '[]' > "$tmp/profiles"
printf '{"Config":null}' > "$tmp/prefs"
printf '%s' "$needs" > "$tmp/state"
run; test "$(cat "$status")" = missing-key
printf '%s' 'tskey-auth-SENTINEL' > "$key"
touch "$tmp/offline"
: > "$tmp/argv"
run; test "$(cat "$status")" = indeterminate; test -s "$key"; ! rg -q '^up ' "$tmp/argv"
rm "$tmp/offline"
run; test "$(cat "$status")" = indeterminate; test -s "$key"
printf '%s' '{"BackendState":"Running","Self":{"ID":"existing","Online":false}}' > "$tmp/state"
: > "$tmp/argv"
run; test "$(cat "$status")" = indeterminate; test -s "$key"; ! rg -q '^up ' "$tmp/argv"
printf '%s' "$needs" > "$tmp/state"
touch "$tmp/profile-error"
: > "$tmp/argv"
run; test "$(cat "$status")" = indeterminate; test -s "$key"; ! rg -q '^up ' "$tmp/argv"
rm "$tmp/profile-error"
printf '[{"id":"old-profile"}]' > "$tmp/profiles"
: > "$tmp/argv"
run; test "$(cat "$status")" = indeterminate; test -s "$key"; ! rg -q '^up ' "$tmp/argv"
printf '[]' > "$tmp/profiles"
printf '{"Config":{"NodeID":"old-node"}}' > "$tmp/prefs"
: > "$tmp/argv"
run; test "$(cat "$status")" = indeterminate; test -s "$key"; ! rg -q '^up ' "$tmp/argv"
printf '{"Config":{"NodeID":"","UserProfile":{"LoginName":"previous"}}}' > "$tmp/prefs"
: > "$tmp/argv"
run; test "$(cat "$status")" = indeterminate; test -s "$key"; ! rg -q '^up ' "$tmp/argv"
printf '{"Config":null}' > "$tmp/prefs"
printf '%s' "$pending" > "$tmp/state"
run; test "$(cat "$status")" = pending-approval; test -s "$key"
printf '%s' "$needs" > "$tmp/state"
printf '%s' "$enrolled" > "$tmp/after-up"
run; test "$(cat "$status")" = enrolled; test ! -e "$key"
# Crash after registration: an already enrolled node must remove the key without reauth.
printf '%s' 'tskey-auth-SENTINEL' > "$key"
: > "$tmp/argv"
run; test ! -e "$key"; ! rg -q '^up ' "$tmp/argv"
run; test "$(cat "$status")" = enrolled
! rg -q 'tskey-auth-SENTINEL' "$tmp/argv" "$tmp/output" "$status"
printf '%s\n' 'bootstrap behavior: PASS'
