#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
switch="$root/tools/r640/switch"
[[ $(git -C "$root" branch --show-current) == main ]] || {
  echo 'run this contract test from main' >&2
  exit 2
}
[[ -z $(git -C "$root" status --porcelain) ]] || {
  echo 'run this contract test from a clean checkout' >&2
  exit 2
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin"
cat > "$tmp/bin/hostname" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "${MOCK_HOST:-r640-0}"
MOCK
cat > "$tmp/bin/nix" <<'MOCK'
#!/usr/bin/env bash
case "$1" in
  eval)
    if [[ "$*" == *systemPackages* ]]; then
      printf '[{"name":"codex-0.162.1","version":"0.162.1"}]\n'
    else
      printf 'r640-0\n'
    fi
    ;;
  build) touch "$MOCK_MARKER/build" ;;
  *) printf 'unexpected nix command: %s\n' "$*" >&2; exit 90 ;;
esac
MOCK
cat > "$tmp/bin/mountpoint" <<'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
cat > "$tmp/bin/zpool" <<'MOCK'
#!/usr/bin/env bash
exit 0
MOCK
cat > "$tmp/bin/sudo" <<'MOCK'
#!/usr/bin/env bash
touch "$MOCK_MARKER/sudo"
exit 91
MOCK
cat > "$tmp/bin/nixos-rebuild" <<'MOCK'
#!/usr/bin/env bash
touch "$MOCK_MARKER/activation"
exit 92
MOCK
chmod +x "$tmp/bin/"*
mkdir -p "$tmp/marker"
export MOCK_MARKER="$tmp/marker"
export PATH="$tmp/bin:$PATH"

if MOCK_HOST=wrong-host "$switch" --check >"$tmp/wrong.out" 2>&1; then
  echo 'wrong host unexpectedly passed' >&2
  exit 1
fi
if ! grep -q 'host must be r640-0' "$tmp/wrong.out"; then
  cat "$tmp/wrong.out" >&2
  echo 'wrong host did not produce the expected refusal' >&2
  exit 1
fi

"$switch" --check
[[ ! -e "$tmp/marker/sudo" && ! -e "$tmp/marker/activation" ]] || {
  echo '--check invoked sudo or activation' >&2
  exit 1
}
"$switch" --dry-run
[[ -e "$tmp/marker/build" ]] || { echo '--dry-run did not build the closure' >&2; exit 1; }
[[ ! -e "$tmp/marker/sudo" && ! -e "$tmp/marker/activation" ]] || {
  echo '--dry-run invoked sudo or activation' >&2
  exit 1
}
printf 'R640 switch contract checks passed.\n'
