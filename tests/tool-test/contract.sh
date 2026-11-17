#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/caller"
cd "$tmp/caller"

export ARBOR_TEST_ROOT="$root"
export ARBOR_TEST_NIX_LOG="$tmp/nix.log"
export PATH="$tmp/bin:$PATH"
cat >"$tmp/bin/nix" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
[[ $PWD == "$ARBOR_TEST_ROOT" ]]
printf '%s\n' "$@" >"$ARBOR_TEST_NIX_LOG"
exit "${ARBOR_TEST_NIX_STATUS:-0}"
MOCK
chmod +x "$tmp/bin/nix"

for lane in fast flake; do
  if [[ ! -x $root/tools/test/$lane ]]; then
    printf 'Missing test entry point: tools/test/%s\n' "$lane" >&2
    exit 1
  fi
  "$root/tools/test/$lane" --help >"$tmp/help"
  grep -Fq "tools/test/$lane" "$tmp/help"
done
[[ ! -e $ARBOR_TEST_NIX_LOG ]]

status=0
"$root/tools/test/fast" --unknown >"$tmp/invalid.out" 2>"$tmp/invalid.err" || status=$?
[[ $status == 2 ]]
grep -Fq 'tools/test/fast' "$tmp/invalid.err"

"$root/tools/test/flake"
printf '%s\n' flake check --no-write-lock-file . >"$tmp/nix.expected"
diff -u "$tmp/nix.expected" "$ARBOR_TEST_NIX_LOG"

status=0
ARBOR_TEST_NIX_STATUS=37 "$root/tools/test/flake" --override-input demo 'path:./with spaces' --no-build || status=$?
[[ $status == 37 ]]
printf '%s\n' --override-input demo 'path:./with spaces' --no-build >>"$tmp/nix.expected"
diff -u "$tmp/nix.expected" "$ARBOR_TEST_NIX_LOG"

printf 'Test entry point contract checks passed.\n'
