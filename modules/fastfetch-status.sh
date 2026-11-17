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
  generation)
    root=${2:-}
    current="$root/run/current-system"
    profiles="$root/nix/var/nix/profiles"
    active=$(readlink -f "$current" 2>/dev/null) || active=
    if [[ ! -L "$current" || -z "$active" || ! -e "$active" ]]; then
      printf 'active system unavailable\n'
      exit 0
    fi
    profile=$(readlink "$profiles/system" 2>/dev/null) || profile=
    profile_number=unknown
    if [[ "$profile" =~ ^system-([0-9]+)-link$ ]]; then profile_number=${BASH_REMATCH[1]}; fi
    profile_target=
    if [[ "$profile_number" != unknown ]]; then
      profile_target=$(readlink -e "$profiles/$profile" 2>/dev/null) || profile_target=
    fi
    if [[ "$profile_target" == "$active" && "$profile_number" != unknown ]]; then
      description="generation $profile_number (profile matches active)"
    else
      matches=()
      for link in "$profiles"/system-*-link; do
        [[ -L "$link" && "${link##*/}" =~ ^system-([0-9]+)-link$ ]] || continue
        number=${BASH_REMATCH[1]}
        target=$(readlink -f "$link" 2>/dev/null) || continue
        if [[ "$target" == "$active" ]]; then matches+=("$number"); fi
      done
      if (( ${#matches[@]} == 1 )); then
        description="generation ${matches[0]} (active)"
      elif (( ${#matches[@]} > 1 )); then
        description="generation ambiguous"
      else
        description="generation unknown"
      fi
      if [[ "$profile_number" != unknown && -n "$profile_target" && "$profile_target" != "$active" ]]; then
        description+="; profile $profile_number differs"
      fi
    fi
    since=$(stat -c %Y "$current" 2>/dev/null) || since=
    now=$(date +%s)
    if [[ "$since" =~ ^[0-9]+$ ]] && (( since <= now )); then
      elapsed=$((now - since))
      printf '%s; active for %sd %sh %sm\n' "$description" "$((elapsed/86400))" "$((elapsed%86400/3600))" "$((elapsed%3600/60))"
    else
      printf '%s; activation time unknown\n' "$description"
    fi
    ;;
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
