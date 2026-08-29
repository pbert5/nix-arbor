#!/usr/bin/env bash
set -euo pipefail

tui=$1
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
printf '{}' >"$work/snapshot.json"
cat >"$work/fake-cli" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${TUI_LOG:?}"
case "$*" in
  *'nodes list'*) printf 'NAME HOST SYSTEM STATE\napi api.example x86_64-linux active\n' ;;
  *'doctor'*) printf 'doctor status=healthy\n' ;;
  *'deployment apply'*) printf 'deployment applied\nsnapshot=test\n  canary:api=succeeded\n' ;;
  *) printf 'deployment snapshot test\nselector=local\nselected=api\nexcluded=\n' ;;
esac
EOF
chmod +x "$work/fake-cli"
export TUI_LOG="$work/log"

"$tui" --snapshot "$work/snapshot.json" --cli "$work/fake-cli" --once 'nodes selected' >"$work/nodes"
grep -q '^NAME HOST' "$work/nodes"
grep -q 'nodes list --scope selected --format table --snapshot' "$work/log"

"$tui" --snapshot "$work/snapshot.json" --cli "$work/fake-cli" --once deployment >"$work/plan"
grep -q 'deployment snapshot test' "$work/plan"

"$tui" --snapshot "$work/snapshot.json" --cli "$work/fake-cli" --once 'deployment apply' >"$work/apply"
grep -q 'confirm APPLY DIGEST' "$work/apply"
if grep -q -- '--acknowledgement' "$work/log"; then exit 1; fi
printf 'confirm APPLY digest fake-backend\n' >"$work/commands"
"$tui" --snapshot "$work/snapshot.json" --cli "$work/fake-cli" --script "$work/commands" >"$work/confirmed"
grep -q 'deployment applied' "$work/confirmed"
grep -q -- '--acknowledgement digest --backend-executable fake-backend' "$work/log"

echo 'tui checks passed'
