#!/usr/bin/env bash
set -eu
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/systemctl" <<'MOCK'
#!/usr/bin/env bash
case "$*" in
  *LoadState*) printf "loaded\n" ;;
  *arbor-registry.service*) printf 'active\n' ;;
  *arbor-registry-transport.service*) printf 'failed\n' ;;
  *arbor-networkd.service*) printf 'inactive\n' ;;
esac
MOCK
cat > "$work/curl" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' '{"initialized":true,"sealed":true}'
MOCK
sed -i "1c#!$(command -v bash)" "$work/systemctl" "$work/curl"
chmod +x "$work/systemctl" "$work/curl"
export PATH="$work:$PATH"
script=modules/fastfetch-status.sh
[[ $(bash "$script" registry) == 'registry: active; transport: failed' ]]
[[ $(bash "$script" manager) == 'configuration unknown; network service: inactive' ]]
[[ $(bash "$script" openbao) == 'sealed' ]]
cat > "$work/systemctl" <<'MOCK'
#!/usr/bin/env bash
printf 'not-found\n'
MOCK
sed -i "1c#!$(command -v bash)" "$work/systemctl"
chmod +x "$work/systemctl"
[[ $(bash "$script" manager) == 'configuration unknown; network service: absent' ]]
cat > "$work/curl" <<'MOCK'
#!/usr/bin/env bash
exit 1
MOCK
sed -i "1c#!$(command -v bash)" "$work/curl"
chmod +x "$work/curl"
[[ $(bash "$script" openbao) == 'seal status unknown; service: absent' ]]
mkdir -p "$work/host/run" "$work/host/nix/var/nix/profiles" "$work/store/a" "$work/store/b"
profiles="$work/host/nix/var/nix/profiles"
ln -s "$work/store/a" "$work/host/run/current-system"
touch -h -d @100000 "$work/host/run/current-system"
printf '#!%s\nprintf "190061\\n"\n' "$(command -v bash)" > "$work/date"
chmod +x "$work/date"
ln -s "$work/store/a" "$profiles/system-7-link"
ln -s system-7-link "$profiles/system"
result=$(bash "$script" generation "$work/host")
[[ "$result" == 'generation 7 (profile matches active); active for 1d 1h 1m' ]]
ln -s "$work/store/b" "$profiles/system-8-link"
ln -sfn system-8-link "$profiles/system"
result=$(bash "$script" generation "$work/host")
[[ "$result" == 'generation 7 (active); profile 8 differs; active for 1d 1h 1m' ]]
ln -s "$work/store/a" "$profiles/system-9-link"
result=$(bash "$script" generation "$work/host")
[[ "$result" == 'generation ambiguous; profile 8 differs; active for 1d 1h 1m' ]]
rm "$work/host/run/current-system"
[[ $(bash "$script" generation "$work/host") == 'active system unavailable' ]]
