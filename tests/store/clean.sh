#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT
mkdir "$tmp/bin"
for command in bash cat grep; do
  ln -s "$(command -v "$command")" "$tmp/bin/$command"
done

smoke=/nix/store/11111111111111111111111111111111-arbor-smoke-test
vm=/nix/store/22222222222222222222222222222222-vm-test-run-arbor
driver=/nix/store/33333333333333333333333333333333-nixos-test-driver-arbor
regular=/nix/store/44444444444444444444444444444444-normal+release?build=1
unrelated=/nix/store/55555555555555555555555555555555-llvm-toolchain
live=/nix/store/66666666666666666666666666666666-smoke-test-live
test_suite=/nix/store/77777777777777777777777777777777-Arbor-Tests
unregistered=/nix/store/88888888888888888888888888888888-unregistered

export FIXTURE_STORE="$tmp"
printf '%s\n' "$regular" "$vm" "$unrelated" "$smoke" "$driver" "$live" "$test_suite" > "$tmp/registered"
printf '%s\n' "$vm" "$smoke" "$driver" "$live" "$test_suite" "$regular" "$unrelated" > "$tmp/preview"
printf '%s\n' nix --extra-experimental-features nix-command path-info --store daemon --all > "$tmp/query"
cat > "$tmp/bin/nix" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' nix "$@" >> "$FIXTURE_STORE/calls"
if [[ $# != 6 || $1 != --extra-experimental-features || $2 != nix-command ||
      $3 != path-info || $4 != --store || $5 != daemon || $6 != --all ]]; then
  printf '%s\n' 'unexpected nix arguments' >&2
  exit 99
fi
cat "$FIXTURE_STORE/registered"
if [[ ${QUERY_STATUS:-0} != 0 ]]; then printf '%s\n' 'fixture query failed' >&2; fi
exit "${QUERY_STATUS:-0}"
MOCK
cat > "$tmp/bin/nix-store" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' nix-store "$@" >> "$FIXTURE_STORE/calls"
if [[ $# -ge 4 && $1 == --store && $2 == daemon && $3 == --check-validity ]]; then
  shift 3
  for path in "$@"; do
    if ! grep -Fxq -- "$path" "$FIXTURE_STORE/registered"; then
      printf 'fixture unregistered path: %s\n' "$path" >&2
      exit 1
    fi
  done
  exit "${CHECK_STATUS:-0}"
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
chmod +x "$tmp/bin/nix" "$tmp/bin/nix-store"

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
grep -Fq -- 'housekeeping' "$tmp/out"
run 0
grep -Fq -- 'liveness is unknown' "$tmp/err"
diff -u "$tmp/preview" "$tmp/out"
diff -u "$tmp/query" "$tmp/calls"
run 0 --list
grep -Fq -- 'liveness is unknown' "$tmp/err"
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

for unavailable in "$unregistered" "${regular%=1}"; do
  run 1 --apply "$smoke" "$unavailable"
  grep -Fq -- "$unavailable" "$tmp/err"
  printf '%s\n' nix-store --store daemon --check-validity "$smoke" "$unavailable" > "$tmp/check"
  diff -u "$tmp/check" "$tmp/calls"
done

printf '%s\n' nix-store --store daemon --check-validity "$regular" "$vm" \
  nix-store --store daemon --delete "$regular" "$vm" > "$tmp/apply"
run 0 --apply "$regular" "$vm"
diff -u "$tmp/apply" "$tmp/calls"
printf '%s\n' nix-store --store daemon --check-validity "$live" \
  nix-store --store daemon --delete "$live" > "$tmp/refused"
DELETE_STATUS=17 run 17 --apply "$live"
grep -Fq 'fixture daemon refused deletion' "$tmp/err"
diff -u "$tmp/refused" "$tmp/calls"

QUERY_STATUS=11 run 11
grep -Fq 'fixture query failed' "$tmp/err"
[[ ! -s "$tmp/out" ]]
diff -u "$tmp/query" "$tmp/calls"
CHECK_STATUS=11 run 11 --apply "$smoke"
printf '%s\n' nix-store --store daemon --check-validity "$smoke" > "$tmp/check"
diff -u "$tmp/check" "$tmp/calls"

printf '%s\n' 'unexpected stdout' >> "$tmp/registered"
run 1 --list
[[ ! -s "$tmp/out" ]]
diff -u "$tmp/query" "$tmp/calls"
: > "$tmp/registered"
run 0
[[ ! -s "$tmp/out" ]]
diff -u "$tmp/query" "$tmp/calls"
run 1 --apply "$smoke"
diff -u "$tmp/check" "$tmp/calls"

mv "$tmp/bin/nix-store" "$tmp/nix-store-fixture"
run 1 --apply "$smoke"
grep -Fq 'nix-store is unavailable' "$tmp/err"
[[ ! -s "$tmp/calls" ]]
run 0
diff -u "$tmp/query" "$tmp/calls"
mv "$tmp/bin/nix" "$tmp/nix-fixture"
run 1
grep -Fq 'nix is unavailable' "$tmp/err"
[[ ! -s "$tmp/calls" ]]

printf '%s\n' 'Store clean fixture checks passed.'
