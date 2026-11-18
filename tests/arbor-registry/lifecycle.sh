#!/usr/bin/env bash
# Contract tests run the public entry point with simulated hosts, services and IPC.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cli=$root/tools/arbor/registry
export fixture
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
cd "$fixture"
mkdir bin
export real_jq
real_jq=$(command -v jq)
export PATH="$fixture/bin:$PATH"
cat > bin/hostname <<'MOCK'
#!/usr/bin/env bash
echo "${actual_host:-r640-0}"
MOCK
cat > bin/ssh <<'MOCK'
#!/usr/bin/env bash
[[ "$*" == "-T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 root-evolver bash -s -- "* ]] || exit 88
shift 8
echo ssh >> "$fixture/routes"
export actual_host=${remote_host:-eVolver} simulated_remote=1
exec "$@"
MOCK
cat > bin/systemctl <<'MOCK'
#!/usr/bin/env bash
set -eu
case "$1:$3" in
  show:--property=ActiveState)
    if [[ -e $fixture/restarted && ${failed_after:-} == "$2" ]]; then echo failed; else echo "${active:-active}"; fi ;;
  show:--property=UnitFileState) echo enabled ;;
  show:--property=User) if [[ $2 == arbor-registry-transport.service ]]; then echo "${transport_user:-arbor-registry-transport}"; else echo arbor-registry; fi ;;
  show:--property=StateDirectory) echo "${state_dir:-${2%.service}-canary-v1}" ;;
  show:--property=LoadState) echo masked ;;
  show:--property=ExecStart)
    bin=/nix/store/0123456789abc-registry/bin
    echo "{ path=$bin/arbor-registryd ; argv[]=$bin/arbor-registryd --config=/etc/arbor-registry/config.json ; }" ;;
  show:--property=EnvironmentFiles) echo "${environment_file:-}" ;;
  show:--property=UnsetEnvironment) echo ;;
  show:--property=Environment) echo 'ARBOR_REGISTRY_STATE_DIR=/var/lib/arbor-registry-transport-canary-v1 ARBOR_REGISTRY_LISTEN= ARBOR_REGISTRY_BOOTSTRAP_PEERS= ARBOR_REGISTRY_DATABASE_ADDRESSES={} ARBOR_REGISTRY_REALM_ID=nix-arbor-live-v1 ARBOR_REGISTRY_PROTOCOL_EPOCH=1 ARBOR_REGISTRY_SOCKET=/run/arbor-registry-transport/transport.sock ARBOR_REGISTRY_SOCKET_TOKEN_FILE=/run/arbor-registry/socket-token' ;;
  *) exit 88 ;;
esac
MOCK
cat > bin/jq <<'MOCK'
#!/usr/bin/env bash
if [[ ${!#} == /etc/arbor-registry/config.json ]]; then
  exec "$real_jq" "${@:1:$#-1}" "$fixture/config.json"
fi
exec "$real_jq" "$@"
MOCK
cat >config.json <<'JSON'
{"authorityIssuers":[],"bootstrapAuthoritiesFile":"/var/lib/arbor-registry-canary-v1/bootstrap-authorities.json","socket":"/run/arbor-registry/registry.sock","stateDir":"/var/lib/arbor-registry-canary-v1","tokenFile":"/run/arbor-registry/socket-token","transportSocket":"/run/arbor-registry-transport/transport.sock"}
JSON
# Simulate paths on a NixOS target while exercising the same path comparisons.
realpath() { echo "${!#}"; }
test() {
  case "$*" in
    '-d /var/lib/arbor-registry-canary-v1'|'-d /var/lib/arbor-registry-transport-canary-v1') return 0 ;;
    '-x /nix/store/0123456789abc-registry/bin/arbor-registry-manager-adapter') [[ -z ${no_adapter:-} ]]; return ;;
    *) builtin test "$@" ;;
  esac
}
export -f realpath test
cat > bin/ss <<'MOCK'
#!/usr/bin/env bash
[[ "$*" == "-Hxl src /run/arbor-registry-transport/transport.sock" ]] || exit 88
if [[ -z ${no_listener:-} ]]; then echo LISTEN; fi
MOCK
printf '#!/usr/bin/env bash\nexit 0\n' > bin/sleep
cat > bin/sudo <<'MOCK'
#!/usr/bin/env bash
set -eu
if [[ ${simulated_remote:-} == 1 ]]; then [[ $1 == -n ]]; shift; fi
if [[ "$*" == '-- systemctl restart arbor-registry-transport.service arbor-registry.service' ]]; then
  echo restart >> "$fixture/log"
  touch "$fixture/restarted"
  exit 0
fi
[[ "$*" == '-u arbor-registry -- /nix/store/0123456789abc-registry/bin/arbor-registry-manager-adapter --config /etc/arbor-registry/config.json' ]]
req=$(cat)
op=$(jq -er '.operation' <<<"$req")
node=${actual_host:-r640-0}
jq -e --arg op "$op" --arg node "$node" '
  .protocol == "arbor-manager/runtime-adapter" and .version == 1 and
  (.data == (if $op == "identity/inspect" then {} elif $op == "identity/init-self"
    then {nodeId:$node,domain:"nix-arbor-live-v1"} else {nodeId:$node} end))' <<<"$req" >/dev/null
echo "$op" >> "$fixture/log"
[[ ${fail_op:-} != "$op" ]] || exit 1
if [[ ${bad_op:-} == "$op" ]]; then echo '{"secret":"do-not-emit"}'; exit 0; fi
if [[ -e $fixture/restarted && -n ${delay:-} && ! -e $fixture/retried ]]; then touch "$fixture/retried"; exit 1; fi
if [[ $op == identity/init-self ]]; then touch "$fixture/initialized"; fi
fingerprint=$(printf '%064d' 0)
if [[ -e $fixture/restarted && -n ${rotate:-} ]]; then fingerprint=$(printf '%064d' 1); fi
if [[ -e $fixture/initialized ]]; then
  data=$(jq -nc --arg node "${foreign:-$node}" --arg fp "$fingerprint" --argjson parents "${parents:-0}" '{nodeId:$node,initialized:true,generation:1,
    publicFingerprint:$fp,localGenesis:true,selfRooted:true,parents:$parents,peers:0,records:{accepted:1,total:1,quarantined:0},projection:{total:1}}')
elif [[ $op == identity/inspect ]]; then
  data='{"nodeId":null,"initialized":false,"localGenesis":false}'
else
  data=$(jq -nc --arg node "$node" --argjson records "${records:-0}" '{nodeId:$node,initialized:false,generation:null,
    publicFingerprint:null,localGenesis:false,selfRooted:false,parents:0,peers:0,records:{accepted:$records,total:$records,quarantined:0},projection:{total:0}}')
fi
if [[ ${extra_op:-} == "$op" ]]; then data=$(jq '.extra="do-not-emit"' <<<"$data"); fi
jq -nc --arg op "$op" --argjson data "$data" '{format:"arbor-manager/runtime-response",version:1,status:"accepted",operation:$op}+$data'
MOCK
sed -i "1c#!$BASH" bin/*
chmod +x bin/*
expect_failure() {
  if "$@" >out 2>err; then echo "unexpected success: $*" >&2; exit 1; fi
  if grep -q 'do-not-emit' out err; then exit 1; fi
}
no_mutation() { ! grep -Eq '^(identity/init-self|restart)$' log; }
: > log
"$cli" --help >/dev/null
expect_failure "$cli" init-self unknown
expect_failure "$cli" invalid r640-0
actual_host=other expect_failure "$cli" init-self r640-0
active=failed expect_failure "$cli" init-self r640-0
transport_user=arbor-registry expect_failure "$cli" init-self r640-0
state_dir=historical expect_failure "$cli" init-self r640-0
environment_file=/test-override expect_failure "$cli" init-self r640-0
no_adapter=1 expect_failure "$cli" init-self r640-0
cp config.json config.clean
jq '.keyDir="/var/lib/arbor-registry/keys"' config.clean >config.json
expect_failure "$cli" init-self r640-0
jq '.stream="fixture"' config.clean >config.json
expect_failure "$cli" init-self r640-0
mv config.clean config.json
"$cli" status r640-0 >/dev/null
: > routes
actual_host=eVolver "$cli" inspect eVolver | jq -e '.initialized == false' >/dev/null
[[ ! -s routes ]]
"$cli" inspect eVolver | jq -e '.initialized == false and .nodeId == null' >/dev/null
[[ $(cat routes) == ssh ]]
remote_host=r640-0 expect_failure "$cli" init-self eVolver
actual_host=eVolver expect_failure "$cli" init-self r640-0
records=2 expect_failure "$cli" init-self r640-0
bad_op=identity/inspect expect_failure "$cli" init-self r640-0
extra_op=registry/summary expect_failure "$cli" init-self r640-0
fail_op=registry/summary expect_failure "$cli" init-self r640-0
expect_failure "$cli" restart-check r640-0
no_mutation
"$cli" init-self eVolver | jq -e '.nodeId == "eVolver" and .generation == 1' >/dev/null
: > routes
actual_host=eVolver "$cli" init-self eVolver >/dev/null
[[ ! -s routes ]]
"$cli" summary eVolver | jq -e '.records.accepted == 1' >/dev/null
parents=1 "$cli" inspect eVolver | jq -e '.selfRooted and .parents == 1' >/dev/null
parents=1 "$cli" summary eVolver | jq -e '.parents == 1' >/dev/null
parents=1 expect_failure "$cli" inspect r640-0
parents=2 expect_failure "$cli" summary eVolver
: > log
foreign=other expect_failure "$cli" init-self r640-0
no_mutation
fail_op=identity/init-self expect_failure "$cli" init-self r640-0
delay=1 "$cli" restart-check r640-0 >/dev/null
[[ -e retried ]]
rm restarted
rotate=1 expect_failure "$cli" restart-check r640-0
rm restarted
no_listener=1 expect_failure "$cli" restart-check r640-0
for unit in arbor-registry-transport.service arbor-registry.service; do
  rm restarted
  failed_after=$unit expect_failure "$cli" restart-check r640-0
done
printf 'Registry lifecycle contract checks passed.\n'
