#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/bin" "$fixture/net/end0/device"
sed -e "s|/run/issue.d|$fixture/issue.d|g" -e "s|/sys/class/net|$fixture/net|g" \
    "$repo/config/machines/raspberry-evolver/console-ips.sh" >"$fixture/console.sh"
printf '%s\n' '#!/usr/bin/env bash' 'cat "$FIXTURE/addresses"' >"$fixture/bin/ip"
printf '%s\n' '#!/usr/bin/env bash' 'printf "%s\n" "$*" >>"$FIXTURE/reloads"' >"$fixture/bin/agetty"
chmod +x "$fixture/bin/"*
export FIXTURE=$fixture PATH="$fixture/bin:$PATH"
banner=$fixture/issue.d/raspberry-evolver.issue
printf '[]\n' >"$fixture/addresses"
bash "$fixture/console.sh"
grep -q 'Waiting for a LAN or Tailscale address' "$banner"
cat >"$fixture/addresses" <<'JSON'
[
  {"ifname":"end0","addr_info":[{"family":"inet","local":"192.0.2.2"}]},
  {"ifname":"tailscale0","addr_info":[{"family":"inet","local":"100.64.0.2"},{"family":"inet6","local":"fd7a:115c:a1e0::2"}]},
  {"ifname":"docker0","addr_info":[{"family":"inet","local":"172.17.0.1"}]}
]
JSON
bash "$fixture/console.sh"
grep -q 'LAN (end0): 192.0.2.2.*ssh ash@192.0.2.2' "$banner"
grep -q 'Tailscale (tailscale0): 100.64.0.2' "$banner"
grep -q 'ssh -6 ash@fd7a:115c:a1e0::2' "$banner"
! grep -q docker0 "$banner"
bash "$fixture/console.sh"
test "$(wc -l <"$fixture/reloads")" = 2
test "$(stat -c %a "$banner")" = 644
