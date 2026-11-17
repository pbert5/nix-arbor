#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin"
for command in bash cat; do
  ln -s "$(command -v "$command")" "$tmp/bin/$command"
done

smoke=/nix/store/11111111111111111111111111111111-arbor-smoke-test
vm=/nix/store/22222222222222222222222222222222-vm-test-run-arbor
driver=/nix/store/33333333333333333333333333333333-nixos-test-driver-arbor
regular=/nix/store/44444444444444444444444444444444-normal+release?build=1
unrelated=/nix/store/55555555555555555555555555555555-llvm-toolchain
live=/nix/store/66666666666666666666666666666666-smoke-test-live

export FIXTURE_STORE="$tmp"
printf '%s\n' "$regular" "$vm" "$unrelated" "$smoke" "$driver" > "$tmp/dead"
printf '%s\n' "$vm" "$smoke" "$driver" "$regular" "$unrelated" > "$tmp/preview"
printf '%s\n' --store daemon --gc --print-dead > "$tmp/query"
cat > "$tmp/bin/nix-store" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" >> "$FIXTURE_STORE/calls"
if [[ $# == 4 && $1 == --store && $2 == daemon && $3 == --gc && $4 == --print-dead ]]; then
  while IFS= read -r path; do printf '%s\n' "$path"; done < "$FIXTURE_STORE/dead"
  if [[ ${QUERY_STATUS:-0} != 0 ]]; then printf '%s\n' 'fixture query failed' >&2; fi
  exit "${QUERY_STATUS:-0}"
fi
if [[ $# -ge 4 && $1 == --store && $2 == daemon && $3 == --delete ]]; then
  if [[ ${DELETE_STATUS:-0} != 0 ]]; then
    printf '%s\n' 'fixture daemon refused deletion' >&2
  fi
  exit "${DELETE_STATUS:-0}"
fi
printf '%s\n' 'unexpected nix-store arguments' >&2
exit 99
MOCK
chmod +x "$tmp/bin/nix-store"

run() (
  expected=$1
  shift
  cd "$tmp"
  : > calls
  status=0
  PATH="$tmp/bin" "$root/tools/store/clean" "$@" > out 2> err || status=$?
  if [[ $status != "$expected" ]]; then
    printf 'Expected exit %s, got %s for %s\n' "$expected" "$status" "$*" >&2
    cat err >&2
    exit 1
  fi
)

run 0 --help
[[ ! -s "$tmp/calls" ]]
grep -Fq -- '--apply' "$tmp/out"
run 0
diff -u "$tmp/preview" "$tmp/out"
diff -u "$tmp/query" "$tmp/calls"
run 0 --list
diff -u "$tmp/preview" "$tmp/out"
diff -u "$tmp/query" "$tmp/calls"

for invalid in '' --apply --ignore-liveness; do
  run 2 "$invalid"
  [[ ! -s "$tmp/calls" ]]
done
run 2 --list "$smoke"
[[ ! -s "$tmp/calls" ]]
for invalid in result "${smoke##*/}" "$smoke/bin/test" "--ignore-liveness" "$smoke"$'\n'"$live"; do
  run 2 --apply "$smoke" "$invalid"
  [[ ! -s "$tmp/calls" ]]
done

for unavailable in "$live" "${regular%=1}"; do
  run 1 --apply "$smoke" "$unavailable"
  grep -Fq -- "$unavailable" "$tmp/err"
  diff -u "$tmp/query" "$tmp/calls"
done

printf '%s\n' --store daemon --gc --print-dead --store daemon --delete "$regular" "$vm" > "$tmp/apply"
run 0 --apply "$regular" "$vm"
diff -u "$tmp/apply" "$tmp/calls"
DELETE_STATUS=17 run 17 --apply "$regular" "$vm"
grep -Fq 'fixture daemon refused deletion' "$tmp/err"
diff -u "$tmp/apply" "$tmp/calls"

QUERY_STATUS=11 run 11
grep -Fq 'fixture query failed' "$tmp/err"
[[ ! -s "$tmp/out" ]]
diff -u "$tmp/query" "$tmp/calls"
QUERY_STATUS=11 run 11 --apply "$smoke"
diff -u "$tmp/query" "$tmp/calls"

printf '%s\n' 'unexpected stdout' >> "$tmp/dead"
run 1 --list
[[ ! -s "$tmp/out" ]]
diff -u "$tmp/query" "$tmp/calls"
run 1 --apply "$smoke"
diff -u "$tmp/query" "$tmp/calls"

: > "$tmp/dead"
run 0
[[ ! -s "$tmp/out" ]]
diff -u "$tmp/query" "$tmp/calls"
run 1 --apply "$smoke"
diff -u "$tmp/query" "$tmp/calls"

mv "$tmp/bin/nix-store" "$tmp/nix-store-fixture"
run 1
grep -Fq 'nix-store is unavailable' "$tmp/err"
[[ ! -s "$tmp/calls" ]]

printf '%s\n' 'Store clean fixture checks passed.'
