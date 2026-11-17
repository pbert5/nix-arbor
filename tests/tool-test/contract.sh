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

checkout="$tmp/cold checkout"
mkdir -p "$checkout"/{bin,tools/test,tests/tool-test,tests/github}
cp "$root/tools/test/fast" "$checkout/tools/test/fast"
printf '#!/usr/bin/env bash\nexit 0\n' >"$checkout/tests/tool-test/contract.sh"
cp "$checkout/tests/tool-test/contract.sh" "$checkout/tests/github/runners-contract.sh"
ln -s "$(command -v bash)" "$checkout/bin/bash"
ln -s "$(command -v dirname)" "$checkout/bin/dirname"
cat >"$checkout/bin/nix" <<'MOCK'
#!/usr/bin/env bash
[[ $3 == eval ]] || exit 43
printf '%s\n' sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=
MOCK
cat >"$checkout/bin/nix-store" <<'MOCK'
#!/usr/bin/env bash
case $1 in
  --print-fixed-path) printf '%s\n' /uncached/nixpkgs ;;
  --check-validity) exit 1 ;;
  *) exit 43 ;;
esac
MOCK
chmod +x "$checkout"/bin/{nix,nix-store} "$checkout"/tests/{tool-test/contract.sh,github/runners-contract.sh}
status=0
PATH="$checkout/bin" "$checkout/tools/test/fast" >"$tmp/cold.out" 2>"$tmp/cold.err" || status=$?
[[ $status == 1 ]] || { printf 'Unexpected fast-test exit for uncached nixpkgs (%s)\n' "$status" >&2; exit 1; }
grep -Fq 'locked nixpkgs source is unavailable' "$tmp/cold.err"

printf 'Test entry point contract checks passed.\n'
