#!/usr/bin/env bash
set -euo pipefail
cli=$1
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
"$cli" --help >/dev/null
printf '%s\n' '{"identity":"node-a","privateKey":"must-not-print"}' >"$work/identity.json"
chmod 600 "$work/identity.json"
"$cli" identity inspect --path "$work/identity.json" >"$work/inspect.json"
jq -e '.operation == "identity/inspect" and .data.privateKey == "<redacted>"' "$work/inspect.json" >/dev/null
printf '#!%s\n' "$(command -v bash)" >"$work/adapter"
cat >>"$work/adapter" <<'EOF'
set -euo pipefail
jq -e '.operation == "identity/import" and .data.privateKey == "must-not-print"' >/dev/null
printf '%s\n' '{"status":"accepted","privateKey":"adapter-secret"}'
EOF
chmod 700 "$work/adapter"
rm -f "$work/raw-output.json"
"$cli" identity import --path "$work/identity.json" --output "$work/raw-output.json" --runtime-executable "$work/adapter" | jq -e '.status == "accepted" and .privateKey == "<redacted>"' >/dev/null
test ! -e "$work/raw-output.json"
printf '%s\n' '{"status":"healthy","healthy":true}' >"$work/status.json"
"$cli" doctor --status "$work/status.json" | jq -e '.healthy == true' >/dev/null
printf '%s\n' '{"target":{"host":"example.invalid","token":"hidden"}}' >"$work/targets.json"
chmod 600 "$work/targets.json"
"$cli" external-target inspect --path "$work/targets.json" --name target | jq -e '.data.token == "<redacted>"' >/dev/null
if "$cli" doctor --status "$work/missing.json" >/dev/null 2>&1; then exit 1; fi
