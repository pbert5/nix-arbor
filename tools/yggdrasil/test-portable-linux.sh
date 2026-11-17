#!/usr/bin/env bash
# Exercise real upstream daemons in private namespaces. The wrapper always
# creates the outer namespace itself, including for callers running as root.
set -euo pipefail
app=$(realpath "$(dirname "$0")/arbor-connect.py")
export app
# Keep NixOS system executables reachable after mounting a private /run.
if [[ -d /run/current-system/sw/bin ]]; then
    export PATH="$(realpath /run/current-system/sw/bin):$PATH"
    export arbor_test_system="$(realpath /run/current-system)"
fi
unshare --user --map-root-user --mount --net --pid --fork --mount-proc bash -euo pipefail <<'INNER'
mount --make-rprivate /
mount -t tmpfs tmpfs /run
if [[ -n ${arbor_test_system:-} ]]; then ln -s "$arbor_test_system" /run/current-system; fi
mkdir /run/netns
work=$(mktemp -d)
trap 'jobs -pr | xargs -r kill 2>/dev/null || true; wait || true; rm -rf "$work"' EXIT
cd "$work"
ip link set lo up
ip netns add operator
ip link add laptop type veth peer name upstream
ip link set upstream netns operator
ip addr add 192.0.2.1/30 dev laptop
ip link set laptop up
ip -n operator addr add 192.0.2.2/30 dev upstream
ip -n operator link set upstream up
ip -n operator link set lo up
umask 077
yggdrasil -genconf -json > server.json
key=$(yggdrasil -useconffile server.json -publickey)
remote=$(yggdrasil -useconffile server.json -address)
client() { python3 "$app" --state-dir "$work/profile" "$@"; }
client init --peer "tls://192.0.2.2:17171?key=$key" > public.json
client identity | cmp - public.json
if client init --peer "tls://192.0.2.2:17171?key=$key" > /dev/null 2>&1; then exit 1; fi
client identity | cmp - public.json
jq --slurpfile guest public.json '.Peers=[] | .AdminListen="none" | .IfName="upstream-ygg"
    | .Listen=["tls://192.0.2.2:17171"] | .MulticastInterfaces=[]
    | .AllowedPublicKeys=[$guest[0].sidecarPublicKey]' server.json > upstream.json
ip netns exec operator yggdrasil -useconffile upstream.json > server.log 2>&1 &
for i in {1..100}; do
    if ip -n operator link show upstream-ygg >/dev/null 2>&1; then break; fi
    sleep 0.1
done
ip netns exec operator python3 -m http.server 18080 --bind "$remote" > remote.log 2>&1 &
client up > client.log 2>&1 & supervisor=$!
for i in {1..50}; do
    if client status > /dev/null && client check "$remote" --port 18080; then break; fi
    if ! kill -0 "$supervisor" 2>/dev/null; then cat client.log >&2; exit 1; fi
    sleep 0.2
done
client status
client check "$remote" --port 18080
guest=$(jq -r .privateAddress public.json)
python3 -m http.server 18081 --bind "$guest" > local.log 2>&1 &
for i in {1..30}; do
    if client check "$guest" --port 18081 >/dev/null 2>&1; then break; fi
    sleep .1
done
client check "$guest" --port 18081
if ip netns exec operator python3 "$app" check "$guest" --port 18081; then
    echo 'Unexpected inbound TCP connection' >&2; exit 1
fi
client down
wait "$supervisor"
if client status > /dev/null; then exit 1; fi
if nft list tables | grep -q arbor_ygg_; then exit 1; fi
test ! -e "$work/profile/session.json"
client identity | cmp - public.json
echo 'Dual-daemon overlay, guest outbound TCP, inbound firewall and teardown passed.'
INNER
