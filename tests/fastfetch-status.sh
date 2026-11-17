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
