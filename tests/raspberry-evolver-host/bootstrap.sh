#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/bootstrap" "$tmp/run" "$tmp/lock"
sed -e "s|/var/lib/raspberry-evolver/bootstrap/tailscale.authkey|$tmp/bootstrap/tailscale.authkey|" -e "s|/run/raspberry-evolver/bootstrap.status|$tmp/run/bootstrap.status|" -e "s|/run/lock/raspberry-evolver-bootstrap.lock|$tmp/lock/bootstrap.lock|" "$repo/config/machines/raspberry-evolver/bootstrap.sh" > "$tmp/bootstrap.sh"
cat > "$tmp/bin/tailscale" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$TEST_DIR/argv"
case "$1" in
  switch) cat "$TEST_DIR/profiles" ;;
  debug) cat "$TEST_DIR/prefs" ;;
  lock) [ ! -e "$TEST_DIR/lock-error" ] || exit 1; cat "$TEST_DIR/lock-state" ;;
  up)
    [ ! -f "$TEST_DIR/after-up" ] || cp "$TEST_DIR/after-up" "$TEST_DIR/state"
    [ ! -f "$TEST_DIR/up-error" ] || cat "$TEST_DIR/up-error" >&2
    exit 1 ;;
  *) [ ! -f "$TEST_DIR/offline" ] || exit 1; cat "$TEST_DIR/state" ;;
esac
MOCK
cat > "$tmp/bin/sleep" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$TEST_DIR/sleeps"
MOCK
chmod +x "$tmp/bin/"*
export TEST_DIR=$tmp PATH="$tmp/bin:$PATH"
key=$tmp/bootstrap/tailscale.authkey
status=$tmp/run/bootstrap.status
run() { bash "$tmp/bootstrap.sh" >"$tmp/output" 2>&1; }
needs='{"BackendState":"NeedsLogin"}'
enrolled='{"BackendState":"Running","HaveNodeKey":true,"Self":{"ID":"node-a","Online":false,"TailscaleIPs":["100.1.2.3"]}}'
pending='{"BackendState":"NeedsMachineAuth"}'
printf '[]' > "$tmp/profiles"
printf '{"Config":null}' > "$tmp/prefs"
printf '{"Enabled":false}' > "$tmp/lock-state"
printf '%s' "$needs" > "$tmp/state"
run; test "$(cat "$status")" = missing-key
test "$(stat -c %a "${status%/*}")" = 755
test "$(stat -c %a "$status")" = 644
printf '%s' 'tskey-auth-SENTINEL' > "$key"
touch "$tmp/offline"; : > "$tmp/argv"
run; test "$(cat "$status")" = indeterminate; test -s "$key"; ! rg -q '^up ' "$tmp/argv"
rm "$tmp/offline"
: > "$tmp/argv"; : > "$tmp/sleeps"
run; test "$(cat "$status")" = indeterminate; test -s "$key"; test "$(rg -c '^up ' "$tmp/argv")" -eq 3; test "$(cat "$tmp/sleeps")" = $'10\n20'
exec 8>"$tmp/lock/bootstrap.lock"; flock -n 8
: > "$tmp/argv"; run; ! rg -q '^up ' "$tmp/argv"
flock -u 8
# Ambiguous crash may leave a fresh-looking state; a later run retries safely.
: > "$tmp/argv"; run; test "$(rg -c '^up ' "$tmp/argv")" -eq 3
printf '%s' "$pending" > "$tmp/state"; : > "$tmp/argv"
run; test "$(cat "$status")" = pending-approval; test -s "$key"; ! rg -q '^up ' "$tmp/argv"
printf '%s' "$enrolled" > "$tmp/state"
touch "$tmp/lock-error"; run; test "$(cat "$status")" = indeterminate; test -s "$key"; rm "$tmp/lock-error"
printf '{"Enabled":true,"NodeKeySigned":false}' > "$tmp/lock-state"
run; test "$(cat "$status")" = pending-approval; test -s "$key"
printf '{"Enabled":false}' > "$tmp/lock-state"
printf '%s' "$needs" > "$tmp/state"
printf '%s\n' 'network temporarily unavailable' > "$tmp/up-error"
run; test "$(cat "$status")" = indeterminate; test -s "$key"
printf '%s\n' 'backend error: invalid authkey' > "$tmp/up-error"; : > "$tmp/argv"
run; test "$(cat "$status")" = needs-new-key; test -s "$key"; test "$(rg -c '^up ' "$tmp/argv")" -eq 1
test "$(stat -c %a "$tmp/run/rejected.sha256")" = 600
: > "$tmp/argv"; run; test "$(cat "$status")" = needs-new-key; ! rg -q '^up ' "$tmp/argv"
printf '%s' 'tskey-auth-REPLACEMENT' > "$key"; rm "$tmp/up-error"
printf '%s' "$enrolled" > "$tmp/after-up"; : > "$tmp/argv"
run; test "$(cat "$status")" = enrolled; test ! -e "$key"; test "$(rg -c '^up ' "$tmp/argv")" -eq 1
: > "$tmp/argv"; run; test "$(cat "$status")" = enrolled; ! rg -q '^up ' "$tmp/argv"
! rg -q 'tskey-auth-(SENTINEL|REPLACEMENT)' "$tmp/argv" "$tmp/output" "$status"
printf '%s\n' 'bootstrap behavior: PASS'
