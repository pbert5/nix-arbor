set -euo pipefail

install -d -m 0755 /run/issue.d
banner=/run/issue.d/raspberry-evolver.issue
temporary=$(mktemp "$banner.XXXXXX")
trap 'rm -f -- "$temporary"' EXIT

addresses=$(ip -j address show up scope global | jq -r '
  .[] | .ifname as $interface | .addr_info[] |
  select(.tentative != true and .deprecated != true) |
  [$interface, .family, .local] | @tsv')
{
  printf '\\n\n'
  found=0
  while IFS=$'\t' read -r interface family address; do
    [[ -n $address ]] || continue
    if [[ $interface == tailscale0 ]]; then
      label=Tailscale
    elif [[ -e /sys/class/net/$interface/device ]]; then
      label=LAN
    else
      continue
    fi
    found=1
    if [[ $family == inet6 ]]; then
      printf '%s (%s): %s  |  ssh -6 ash@%s\n' "$label" "$interface" "$address" "$address"
    else
      printf '%s (%s): %s  |  ssh ash@%s\n' "$label" "$interface" "$address" "$address"
    fi
  done <<<"$addresses"
  if (( ! found )); then printf 'Waiting for a LAN or Tailscale address.\n'; fi
} >"$temporary"

if ! cmp -s "$temporary" "$banner"; then
  chmod 0644 "$temporary"
  mv -f -- "$temporary" "$banner"
  agetty --reload
fi
