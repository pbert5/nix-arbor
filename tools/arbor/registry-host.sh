# Host-side implementation of tools/arbor/registry, also streamed over SSH.
set -euo pipefail
shopt -s inherit_errexit

die() { echo "registry: $*" >&2; exit 1; }
property() { systemctl show "$1" --property="$2" --value; }
config=/etc/arbor-registry/config.json
registry=arbor-registry.service
transport=arbor-registry-transport.service

check_units() {
  local unit state enabled active start pattern env setting dir
  for unit in "$registry" "$transport"; do
    state=${unit%.service}-canary-v1
    enabled=$(property "$unit" UnitFileState)
    active=$(property "$unit" ActiveState)
    echo "$host $unit: $enabled, $active" >&2
    [[ $enabled == enabled && $active == active ]] || die "$unit must be enabled and active"
    [[ $(property "$unit" User) == arbor-registry && $(property "$unit" StateDirectory) == "$state" ]] ||
      die "unexpected owner or StateDirectory for $unit"
    dir=/var/lib/$state
    [[ $(realpath -e -- "$dir") == "$dir" ]] && test -d "$dir" || die "unexpected state path for $unit"
  done
  jq -e '(has("keyDir") or has("stream") | not) and
    .stateDir == "/var/lib/arbor-registry-canary-v1" and
    .bootstrapAuthoritiesFile == (.stateDir + "/bootstrap-authorities.json") and .authorityIssuers == [] and
    .socket == "/run/arbor-registry/registry.sock" and .tokenFile == "/run/arbor-registry/socket-token" and
    .transportSocket == "/run/arbor-registry-transport/transport.sock"' "$config" >/dev/null ||
    die 'unexpected Registry config'
  local env_files unset_env
  env_files=$(property "$transport" EnvironmentFiles)
  unset_env=$(property "$transport" UnsetEnvironment)
  [[ -z $env_files && -z $unset_env ]] || die 'transport environment overrides require review'
  env=" $(property "$transport" Environment) "
  for setting in ARBOR_REGISTRY_STATE_DIR=/var/lib/arbor-registry-transport-canary-v1 \
      ARBOR_REGISTRY_LISTEN= ARBOR_REGISTRY_BOOTSTRAP_PEERS= 'ARBOR_REGISTRY_DATABASE_ADDRESSES={}' \
      ARBOR_REGISTRY_REALM_ID=nix-arbor-live-v1 ARBOR_REGISTRY_PROTOCOL_EPOCH=1 ARBOR_REGISTRY_SOCKET=/run/arbor-registry-transport/transport.sock \
      ARBOR_REGISTRY_SOCKET_TOKEN_FILE=/run/arbor-registry/socket-token; do
    [[ $env == *" $setting "* ]] || die 'unexpected transport configuration'
  done
  for unit in arbor-runtime-status.timer arbor-runtime-status.service; do
    [[ $(property "$unit" LoadState) == masked ]] || die "$unit must be masked"
  done
  start=$(property "$registry" ExecStart)
  pattern='^\{ path=(/nix/store/[a-z0-9]+-[^ /;]+/bin)/arbor-registryd ; argv\[\]=([^ ]+) --config=/etc/arbor-registry/config.json ;'
  [[ $start =~ $pattern ]] || die 'unrecognized Registry ExecStart'
  [[ ${BASH_REMATCH[2]} == "${BASH_REMATCH[1]}/arbor-registryd" ]] || die 'unexpected Registry executable'
  adapter=${BASH_REMATCH[1]}/arbor-registry-manager-adapter
  test -x "$adapter" || die 'running Registry package has no Manager adapter'
}

call_adapter() {
  local op=$1 data='{}'
  case $op in
    identity/init-self) data=$(jq -nc --arg node "$host" '{nodeId:$node,domain:"nix-arbor-live-v1"}') ;;
    registry/summary) data=$(jq -nc --arg node "$host" '{nodeId:$node}') ;;
  esac
  jq -nc --arg op "$op" --argjson data "$data" \
    '{protocol:"arbor-manager/runtime-adapter",version:1,operation:$op,data:$data}' |
    "${privilege[@]}" -u arbor-registry -- "$adapter" --config "$config"
}

# Allow only the pinned public response shapes. Never echo an unvalidated reply.
validate() {
  jq -ces --arg host "$host" --arg op "$1" '
    def nonneg: type == "number" and . >= 0 and . == floor;
    def emptyInspect: $op == "identity/inspect" and
      keys == ["format","initialized","localGenesis","nodeId","operation","status","version"] and
      .nodeId == null and .initialized == false and .localGenesis == false;
    def snapshot: keys == ["format","generation","initialized","localGenesis","nodeId","operation",
      "parents","peers","projection","publicFingerprint","records","selfRooted","status","version"] and
      .nodeId == $host and .parents == 0 and .peers == 0 and
      (.records | keys == ["accepted","quarantined","total"] and all(.[]; nonneg)
        and .quarantined == 0 and .total == .accepted) and
      (.projection | keys == ["total"] and (.total | nonneg)) and
      .projection.total <= .records.accepted and
      ((.initialized == true and .localGenesis == true and .selfRooted == true and .generation == 1 and
        .records.accepted >= 1 and .projection.total >= 1 and
        (.publicFingerprint | type == "string" and test("^[a-f0-9]{64}$") and length == 64)) or
       ($op == "registry/summary" and .initialized == false and .localGenesis == false and .selfRooted == false
        and has("generation") and .generation == null and has("publicFingerprint") and .publicFingerprint == null
        and .records.total == 0));
    select(length == 1) | .[0] |
    select(.format == "arbor-manager/runtime-response" and .version == 1 and .status == "accepted" and
      .operation == $op and (emptyInspect or snapshot)) |
    {nodeId,initialized,localGenesis} + (if .nodeId == null then {} else
      {generation,publicFingerprint,selfRooted,parents,peers,records,projection} end)
  ' 2>/dev/null || die "unexpected $1 response or conflicting local state on $host"
}

query() {
  local raw
  raw=$(call_adapter "$1") || die "$1 failed on $host; check service, sudo and identity conflicts"
  validate "$1" <<<"$raw"
}

identity() { jq -cS 'del(.records,.projection)'; }

run() {
  local action=$1 host=$2 adapter before after summary raw attempt
  local -a privilege=(sudo)
  if [[ $host == eVolver ]]; then privilege+=(-n); fi
  [[ $(hostname) == "$host" ]] || die "expected hostname $host"
  check_units
  case $action in
    status) echo "$host Registry canary configuration verified"; return ;;
  esac
  before=$(query identity/inspect)
  case $action in
    inspect) echo "$before"; return ;;
    summary|init-self)
      summary=$(query registry/summary)
      if [[ $(jq -r .initialized <<<"$before") == true ]]; then
        [[ $(identity <<<"$summary") == "$(identity <<<"$before")" ]] || die 'inspect and summary disagree'
      else
        [[ $(jq -r .initialized <<<"$summary") == false ]] || die 'inspect and summary disagree'
      fi
      if [[ $action == summary ]]; then echo "$summary"; return; fi
      # The daemon checks for unclaimed keys and verifies the domain on repeats.
      after=$(query identity/init-self)
      if [[ $(jq -r .initialized <<<"$before") == true ]]; then
        [[ $(identity <<<"$before") == "$(identity <<<"$after")" ]] || die 'existing identity changed during init-self'
      fi
      summary=$(query registry/summary)
      [[ $(identity <<<"$after") == "$(identity <<<"$summary")" ]] || die 'post-init identity mismatch'
      echo "$summary"
      ;;
    restart-check)
      [[ $(jq -r .initialized <<<"$before") == true ]] || die 'restart-check requires an initialized identity'
      "${privilege[@]}" -- systemctl restart "$registry"
      check_units
      for attempt in {1..10}; do
        if raw=$(call_adapter identity/inspect); then
          after=$(validate identity/inspect <<<"$raw")
          [[ $(identity <<<"$before") == "$(identity <<<"$after")" ]] || die 'identity changed after restart'
          echo "$after"
          return
        fi
        (( attempt == 10 )) || sleep 1
      done
      die 'Registry adapter unavailable after restart'
      ;;
    *) die 'unknown Registry command' ;;
  esac
}

run "$@"
