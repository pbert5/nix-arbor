#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/profiles" "$tmp/systems"
for i in 1 2 3 4 5; do
  mkdir "$tmp/systems/$i"
  ln -s "$tmp/systems/$i" "$tmp/profiles/system-$i-link"
done
ln -s "$tmp/systems/5" "$tmp/current"
ln -s "$tmp/systems/4" "$tmp/booted"
sed -e "s|/run/lock/raspberry-evolver-maintenance.lock|$tmp/lock|" -e "s|/nix/var/nix/profiles/system|$tmp/profiles/system|" -e "s|/run/current-system|$tmp/current|" -e "s|/run/booted-system|$tmp/booted|" "$repo/config/machines/raspberry-evolver/maintenance.sh" > "$tmp/maintenance.sh"
cat > "$tmp/bin/nix-env" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$TEST_DIR/deleted"
MOCK
cat > "$tmp/bin/nix-store" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$TEST_DIR/gc"
MOCK
chmod +x "$tmp/bin/"*
export TEST_DIR=$tmp PATH="$tmp/bin:$PATH"
bash "$tmp/maintenance.sh"
test "$(cat "$tmp/deleted")" = "--profile $tmp/profiles/system --delete-generations 2 1" || test "$(cat "$tmp/deleted")" = "--profile $tmp/profiles/system --delete-generations 1 2"
test "$(cat "$tmp/gc")" = --gc
rm "$tmp/deleted" "$tmp/gc" "$tmp/booted"
ln -s "$tmp/systems/1" "$tmp/booted"
bash "$tmp/maintenance.sh"
! rg -q ' 1( |$)' "$tmp/deleted"
rm "$tmp/deleted" "$tmp/gc" "$tmp/booted"
ln -s "$tmp/systems" "$tmp/booted"
if bash "$tmp/maintenance.sh"; then exit 1; fi
test ! -e "$tmp/deleted" && test ! -e "$tmp/gc"
printf '%s\n' 'maintenance behavior: PASS'
