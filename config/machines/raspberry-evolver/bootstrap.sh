#!/usr/bin/env bash
set -eu
key=/var/lib/raspberry-evolver/bootstrap/tailscale.authkey
status=/run/raspberry-evolver/bootstrap.status
mkdir -p "${status%/*}"
umask 077
state() { printf '%s\n' "$1" > "$status"; }
inspect() {
  local response
  response=$(timeout 15 tailscale status --json 2>/dev/null) || { state indeterminate; return 2; }
  if jq -e '.BackendState == "Running" and .Self != null and .Self.Online == true and (.Self.TailscaleIPs | length > 0)' >/dev/null <<<"$response"; then
    state enrolled
    rm -f -- "$key"
    return 0
  fi
  if jq -e '.BackendState == "NeedsMachineAuth"' >/dev/null <<<"$response"; then
    state pending-approval
    return 0
  fi
  # Status alone cannot establish whether a prior identity is persisted.
  if jq -e '.BackendState == "NeedsLogin" and ((.Self.ID // "") == "")' >/dev/null <<<"$response"; then
    local profiles prefs
    profiles=$(timeout 15 tailscale switch --list --json 2>/dev/null) || { state indeterminate; return 2; }
    prefs=$(timeout 15 tailscale debug prefs 2>/dev/null) || { state indeterminate; return 2; }
    if jq -e 'type == "array" and length == 0' >/dev/null <<<"$profiles" &&
       jq -e 'type == "object" and has("Config") and .Config == null' >/dev/null <<<"$prefs"; then
      return 1
    fi
  fi
  state indeterminate
  return 2
}
state waiting
result=0
inspect || result=$?
[ "$result" -eq 1 ] || exit 0
if [ ! -s "$key" ]; then
  state missing-key
  exit 0
fi
state retrying
# Neither the key contents nor daemon output are sent to the journal.
timeout 60 tailscale up --auth-key="file:$key" --accept-dns=false >/dev/null 2>&1 || true
result=0
inspect || result=$?
[ "$result" -eq 0 ] || state indeterminate
