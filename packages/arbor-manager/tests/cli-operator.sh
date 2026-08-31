#!/usr/bin/env bash
set -euo pipefail
cli=$1
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
printf '#!/bin/sh\nprintf "tui-help\\n"\n' >"$work/arbor-manager-tui"
chmod 700 "$work/arbor-manager-tui"
PATH="$work:$PATH" "$cli" tui --help | grep -qx tui-help
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
"$cli" identity import --path "$work/identity.json" --runtime-executable "$work/adapter" | jq -e '.status == "accepted" and (has("privateKey") | not)' >/dev/null
if "$cli" identity import --path "$work/identity.json" --output "$work/raw-output.json" --runtime-executable "$work/adapter" >/dev/null 2>&1; then exit 1; fi
test ! -e "$work/raw-output.json"
if "$cli" recovery export --path "$work/identity.json" >/dev/null 2>"$work/recovery-error"; then exit 1; fi
grep -q 'requires --runtime-executable' "$work/recovery-error"
printf '%s\n' '{"status":"healthy","healthy":true,"generatedAt":'"$(date +%s)"'}' >"$work/status.json"
"$cli" doctor --status "$work/status.json" | jq -e '.healthy == true' >/dev/null
printf '%s\n' '{"target":{"host":"example.invalid","token":"hidden"}}' >"$work/targets.json"
chmod 600 "$work/targets.json"
"$cli" external-target inspect --path "$work/targets.json" --name target | jq -e '.data.token == "<redacted>"' >/dev/null
if "$cli" doctor --status "$work/missing.json" >/dev/null 2>&1; then exit 1; fi

cat >"$work/identity-adapter" <<'EOF'
#!/bin/sh
set -eu
request=$(cat)
operation=$(printf '%s' "$request" | jq -r .operation)
case "$operation" in
  identity/inspect) jq -n '{nodeId:"node-a", initialized:true, generation:1, publicFingerprint:"fp", localGenesis:true, selfRooted:true, parents:[], peers:[], privateKey:"must-not-print"}' ;;
  identity/init-self) jq -n '{status:"accepted", nodeId:"node-a", initialized:true, generation:1, publicFingerprint:"fp", localGenesis:true, privateKey:"must-not-print"}' ;;
  registry/summary) jq -n '{records:{total:219,accepted:2,quarantined:217},projection:{total:1},localIdentity:{nodeId:"node-a",initialized:false,localGenesis:false,conflict:false}, privateKey:"must-not-print"}' ;;
  *) exit 1 ;;
esac
EOF
chmod 700 "$work/identity-adapter"
"$cli" identity inspect --runtime-executable "$work/identity-adapter" | jq -e '.nodeId == "node-a" and .privateKey == null' >/dev/null
"$cli" identity init-self --node-id node-a --domain example.internal --runtime-executable "$work/identity-adapter" | jq -e '.nodeId == "node-a" and .localGenesis == true and .privateKey == null' >/dev/null
"$cli" registry summary --node-id node-a --runtime-executable "$work/identity-adapter" | jq -e '.records.total == 219 and .localIdentity.conflict == false and .privateKey == null' >/dev/null
