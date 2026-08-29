#!/usr/bin/env bash
set -euo pipefail
cli=$1
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
printf '%s\n' '{"identity":"node-a","privateKey":"must-not-print"}' >"$work/identity.json"
chmod 600 "$work/identity.json"
"$cli" identity inspect --path "$work/identity.json" >"$work/inspect.json"
jq -e '.operation == "identity/inspect" and .data.privateKey == "<redacted>"' "$work/inspect.json" >/dev/null
"$cli" identity import --path "$work/identity.json" --output "$work/imported.json" >"$work/import.json"
test "$(stat -c '%a' "$work/imported.json")" = 600
printf '%s\n' '{"status":"healthy","healthy":true}' >"$work/status.json"
"$cli" doctor --status "$work/status.json" | jq -e '.healthy == true' >/dev/null
printf '%s\n' '{"target":{"host":"example.invalid","token":"hidden"}}' >"$work/targets.json"
chmod 600 "$work/targets.json"
"$cli" external-target inspect --path "$work/targets.json" --name target | jq -e '.data.token == "<redacted>"' >/dev/null
if "$cli" doctor --status "$work/missing.json" >/dev/null 2>&1; then exit 1; fi
