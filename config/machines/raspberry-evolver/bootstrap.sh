#!/usr/bin/env bash
set -eu
key=/var/lib/raspberry-evolver/bootstrap/tailscale.authkey
status=/run/raspberry-evolver/bootstrap.status
rejected=${key%/*}/rejected.sha256
budget=${status%/*}/attempts
firmware_key() {
  [ "$#" -eq 0 ] || [ -z "${FIRMWARE_KEY_HELPER:-}" ] || python3 "$FIRMWARE_KEY_HELPER" "$1" "$FIRMWARE_MOUNT" "$key"
}
install -d -m 0755 "${status%/*}"
umask 077
exec 9>/run/lock/raspberry-evolver-bootstrap.lock
flock -n 9 || exit 0
state() { printf '%s\n' "$1" > "$status"; chmod 0644 "$status"; }
inspect() {
  local response lock_status
  response=$(timeout 15 tailscale status --json 2>/dev/null) || { state indeterminate; return 2; }
  if jq -e '.BackendState == "Running" and .HaveNodeKey == true and (.Self.ID // "") != "" and (.Self.TailscaleIPs | type == "array" and length > 0)' >/dev/null <<<"$response"; then
    lock_status=$(timeout 15 tailscale lock status --json 2>/dev/null) || { state indeterminate; return 2; }
    if jq -e '.Enabled == true and .NodeKeySigned == false' >/dev/null <<<"$lock_status"; then
      state pending-approval
      return 2
    fi
    jq -e '.Enabled == false or (.Enabled == true and .NodeKeySigned == true)' >/dev/null <<<"$lock_status" || { state indeterminate; return 2; }
    state enrolled
    if ! firmware_key cleanup || ! rm -f -- "$key" "$rejected"; then
      state enrolled-cleanup-failed
    fi
    return 0
  fi
  if jq -e '.BackendState == "NeedsMachineAuth"' >/dev/null <<<"$response"; then
    state pending-approval
    return 2
  fi
  # NeedsLogin is not proof of failure or success, but permits another
  # non-forced attempt with the supplied key under CR-01.
  if jq -e '.BackendState == "NeedsLogin"' >/dev/null <<<"$response"; then return 1; fi
  state indeterminate
  return 2
}
state waiting
result=0
inspect || result=$?
[ "$result" -eq 1 ] || exit 0
stage=0
firmware_key stage || stage=$?
case "$stage" in
  0) ;;
  2) state invalid-firmware-key; exit 0 ;;
  *) state firmware-key-unavailable; exit 0 ;;
esac
if [ ! -s "$key" ]; then
  state missing-key
  exit 0
fi
fingerprint=$(sha256sum < "$key")
if [ -f "$rejected" ] && [ "$(cat "$rejected")" = "$fingerprint" ]; then
  state needs-new-key
  exit 0
fi
# Limit unattended attempts per key per boot, allowing late DHCP a retry.
if [ -n "${FIRMWARE_KEY_HELPER:-}" ]; then
  attempts=0
  if [ -f "$budget" ]; then
    read -r previous count <"$budget" || true
    if [ "${previous:-}" = "${fingerprint%% *}" ]; then attempts=$count; fi
  fi
  if [ "$attempts" -ge 3 ]; then
    state retry-limit
    exit 0
  fi
  printf '%s %s\n' "${fingerprint%% *}" "$((attempts + 1))" >"$budget"
fi
for delay in 10 20 0; do
  state retrying
  output=$(timeout 60 tailscale up --auth-key="file:$key" --accept-dns=false 2>&1) || true
  result=0
  inspect || result=$?
  [ "$result" -ne 0 ] || exit 0
  [ "$result" -eq 1 ] || exit 0
  if [ "$output" = 'backend error: invalid authkey' ]; then
    printf '%s\n' "$fingerprint" > "$rejected"
    state needs-new-key
    exit 0
  fi
  [ "$delay" -eq 0 ] || sleep "$delay"
done
state indeterminate
