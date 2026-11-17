#!/usr/bin/env bash
# These are local observations, not authenticated health checks.
service_state() {
  local state load
  load=$(timeout 1 systemctl show --property=LoadState --value "$1" 2>/dev/null) || { printf unknown; return; }
  if [[ "$load" == not-found ]]; then printf absent; return; fi
  state=$(timeout 1 systemctl show --property=ActiveState --value "$1" 2>/dev/null) || state=unknown
  printf '%s' "${state:-unknown}"
}
case "$1" in
  registry)
    printf 'registry: %s; transport: %s\n' "$(service_state arbor-registry.service)" "$(service_state arbor-registry-transport.service)"
    ;;
  manager)
    printf '%s; network service: %s\n' "${2:-configuration unknown}" "$(service_state arbor-networkd.service)"
    ;;
  openbao)
    response=$(curl -q --fail --noproxy '*' --silent --max-time 1 http://127.0.0.1:8200/v1/sys/seal-status 2>/dev/null) || response=
    state=$(printf '%s' "$response" | jq -r 'if .initialized == false then "uninitialized" elif .initialized == true and .sealed == true then "sealed" elif .initialized == true and .sealed == false then "unsealed" else "unknown" end' 2>/dev/null) || state=unknown
    if [[ "${state:-unknown}" == unknown ]]; then
      printf 'seal status unknown; service: %s\n' "$(service_state openbao.service)"
    else
      printf '%s\n' "$state"
    fi
    ;;
esac
