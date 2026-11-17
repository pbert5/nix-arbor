#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

export MOCK_PRIMARY="$tmp/r640"
export MOCK_HEAD=0123456789abcdef0123456789abcdef01234567
export MOCK_CALLS="$tmp/calls" MOCK_ROLLBACK="$tmp/rollback"
checkout="$tmp/invoking checkout"
mkdir -p "$tmp/bin" "$checkout/tools/r640" "$MOCK_PRIMARY/tools/r640" \
  "$MOCK_PRIMARY/mypool/"{docker_data,nix-build} \
  "$MOCK_PRIMARY/current-system/bin" "$MOCK_PRIMARY/store/codex-switch/bin"
cp -a "$root/tools/machines" "$checkout/tools/"
cp -a "$checkout/tools/machines" "$MOCK_PRIMARY/tools/"

# Exercise the real legacy guard with the host paths redirected into the fixture.
# shellcheck disable=SC2016
sed -e 's|/home/ash/documents/nix-arbor|$MOCK_PRIMARY|g' \
  -e 's|/mypool|$MOCK_PRIMARY/mypool|g' \
  -e 's|/run/current-system/sw/bin|$MOCK_PRIMARY/current-system/bin|g' \
  "$root/tools/r640/switch" > "$MOCK_PRIMARY/tools/r640/switch"
cat > "$MOCK_PRIMARY/current-system/bin/codex" <<'MOCK'
#!/usr/bin/env bash
[[ $* == --version ]]
printf 'codex-cli %s\n' "${MOCK_CODEX_VERSION:-1.2.3}"
MOCK
cat > "$MOCK_PRIMARY/store/codex-switch/bin/codex-switch" <<'MOCK'
#!/usr/bin/env bash
[[ $* == --help ]]
MOCK
ln -s "$MOCK_PRIMARY/store/codex-switch/bin/codex-switch" "$MOCK_PRIMARY/current-system/bin/codex-switch"
chmod +x "$MOCK_PRIMARY/tools/r640/switch" "$MOCK_PRIMARY/current-system/bin/codex" \
  "$MOCK_PRIMARY/store/codex-switch/bin/codex-switch"
cp -p "$MOCK_PRIMARY/tools/r640/switch" "$checkout/tools/r640/switch"

cat > "$tmp/bin/mock" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail

command=${0##*/}
# The SSH payload is executed below, where aliases, arguments, and effects can
# be checked independently of the payload's particular shell formatting.
case $command in
  ssh)
    if [[ $1 == -t ]]; then
      printf 'ssh<-t><%s>\n' "$2"
    else
      printf 'ssh<%s>\n' "$1"
    fi >> "$MOCK_CALLS"
    ;;
  *)
    {
      printf '%s' "$command"
      printf '<%s>' "$@"
      printf '\n'
    } >> "$MOCK_CALLS"
    ;;
esac

case $command in
  git)
    repo=$PWD
    if [[ $1 == -C ]]; then
      repo=$2
      shift 2
    fi
    head=$MOCK_HEAD
    if [[ $repo == "$MOCK_PRIMARY" ]]; then
      head=${MOCK_REMOTE_HEAD:-$MOCK_HEAD}
      if [[ -n ${MOCK_MOVED_HEAD-} ]] && grep -q '^nix<eval>' "$MOCK_CALLS"; then
        head=$MOCK_MOVED_HEAD
      fi
    fi
    case "$*" in
      'rev-parse --show-toplevel') printf '%s\n' "$repo" ;;
      'branch --show-current') printf '%s\n' "${MOCK_BRANCH-main}" ;;
      'status --porcelain')
        [[ ! ${MOCK_GIT_STATUS_FAILURE-} ]] || exit 98
        printf '%s' "${MOCK_DIRTY-}"
        ;;
      'rev-parse --short HEAD') printf '%s\n' "${head:0:7}" ;;
      'rev-parse --verify HEAD'|'rev-parse HEAD') printf '%s\n' "$head" ;;
      *) exit 90 ;;
    esac
    ;;
  hostname) [[ $* == -s ]] && printf '%s\n' "${MOCK_HOST-eVolver}" ;;
  nix)
    case "$1:$2:$3" in
      eval:--raw:*#nixosConfigurations.eVolver.config.networking.hostName)
        printf '%s\n' "${MOCK_FLAKE_HOST-eVolver}"
        ;;
      eval:--raw:*#nixosConfigurations.r640-0.config.networking.hostName)
        printf '%s\n' "${MOCK_FLAKE_HOST-r640-0}"
        ;;
      eval:--json:*#nixosConfigurations.r640-0.config.environment.systemPackages)
        jq -cn --arg path "$MOCK_PRIMARY/store/codex-switch" '[
          {name:"codex-1.2.3",version:"1.2.3",path:"/fixture/codex"},
          {name:"codex-switch-4.5.6",version:"4.5.6",path:$path}
        ]'
        ;;
      build:--no-link:*#nixosConfigurations.*.config.system.build.toplevel) ;;
      *) exit 91 ;;
    esac
    ;;
  mountpoint) [[ $* == "-q $MOCK_PRIMARY/mypool" && ! ${MOCK_NO_MOUNT-} ]] ;;
  zpool) [[ $* == 'list -H mypool' && ! ${MOCK_NO_POOL-} ]] ;;
  nix-env) printf '1 fixture generation\n' ;;
  sudo)
    case "$1" in
      -v|install|nixos-rebuild) ;;
      tee) cat > "$MOCK_ROLLBACK" ;;
      *) exit 92 ;;
    esac
    ;;
  nixos-rebuild)
    [[ ! ${NIX_SSHOPTS+x} && ! ${NIXOS_REBUILD_SSH_DEFAULT_OPTS+x} ]]
    ;;
  ssh)
    [[ $1 != -t ]] || shift
    case $1 in
      root-evolver)
        [[ $# -eq 3 && $2 == hostname && $3 == -s ]] || exit 93
        [[ ! ${MOCK_SSH_FAILURE-} ]] || exit 255
        printf '%s\n' "${MOCK_REMOTE_HOST-eVolver}"
        ;;
      r640-0)
        [[ $# -eq 2 ]] || exit 94
        cd() {
          [[ $* == /home/ash/documents/nix-arbor ]] || return 95
          builtin cd "$MOCK_PRIMARY"
        }
        export MOCK_HOST=${MOCK_REMOTE_HOST-r640-0}
        eval "$2"
        ;;
      *) exit 96 ;;
    esac
    ;;
  *) exit 97 ;;
esac
MOCK
chmod +x "$tmp/bin/mock"
for command in git hostname nix mountpoint zpool nix-env sudo nixos-rebuild ssh; do
  ln -s mock "$tmp/bin/$command"
done
export PATH="$tmp/bin:$PATH"
cd "$tmp"

run() {
  local expected=$1 status=0
  shift
  : > "$MOCK_CALLS"
  "$@" > "$tmp/out" 2>&1 || status=$?
  if [[ $status != "$expected" ]]; then
    cat "$tmp/out" "$MOCK_CALLS" >&2
    printf 'Expected exit %s, got %s from %s\n' "$expected" "$status" "$*" >&2
    exit 1
  fi
}

called() { grep -Fxq -- "$1" "$MOCK_CALLS"; }
output() { grep -Fq -- "$1" "$tmp/out"; }
no_activation() {
  if grep -Eq '^(sudo|nixos-rebuild)<' "$MOCK_CALLS"; then
    cat "$MOCK_CALLS" >&2
    exit 1
  fi
}

evolver="$checkout/tools/machines/evolver/switch"
evolver_remote="$checkout/tools/machines/evolver/remote-switch"
r640="$MOCK_PRIMARY/tools/machines/r640-0/switch"
r640_remote="$checkout/tools/machines/r640-0/remote-switch"
moved_head=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

for command in "$evolver" "$evolver_remote" "$r640" "$r640_remote"; do
  run 0 "$command" --help
  output 'Usage:'
  [[ ! -s $MOCK_CALLS ]]
  run 2 "$command" --dry-run unexpected
  [[ ! -s $MOCK_CALLS ]]
done

run 0 "$evolver" --check
called "nix<eval><--raw><$checkout#nixosConfigurations.eVolver.config.networking.hostName>"
called 'hostname<-s>'
no_activation
run 1 env MOCK_FLAKE_HOST=wrong "$evolver"
output "declares hostname 'wrong'"
no_activation
run 1 env MOCK_HOST=wrong "$evolver"
output 'host must be eVolver'
no_activation
run 0 "$evolver"
called "sudo<nixos-rebuild><switch><--flake><$checkout#eVolver>"

run 0 "$evolver_remote" --check
called 'ssh<root-evolver>'
no_activation
run 1 env MOCK_REMOTE_HOST=wrong "$evolver_remote"
output 'host must be eVolver'
no_activation
run 255 env MOCK_SSH_FAILURE=1 "$evolver_remote"
no_activation
run 0 env NIX_SSHOPTS='-o HostName=wrong' NIXOS_REBUILD_SSH_DEFAULT_OPTS='-o StrictHostKeyChecking=no' "$evolver_remote"
called 'ssh<root-evolver>'
called "nixos-rebuild<switch><--flake><$checkout#eVolver><--target-host><root-evolver>"
for command in "$evolver" "$evolver_remote"; do
  run 0 env MOCK_HOST=wrong "$command" --dry-run
  called "nix<build><--no-link><$checkout#nixosConfigurations.eVolver.config.system.build.toplevel>"
  no_activation
  if grep -Eq '^(ssh|hostname)<' "$MOCK_CALLS"; then exit 1; fi
done

run 1 "$checkout/tools/machines/r640-0/switch" --check
output 'expected primary checkout'
run 0 env MOCK_HOST=r640-0 "$r640" --check
called "nix<eval><--raw><$MOCK_PRIMARY#nixosConfigurations.r640-0.config.networking.hostName>"
called "mountpoint<-q><$MOCK_PRIMARY/mypool>"
called 'zpool<list><-H><mypool>'
no_activation

run 1 env MOCK_REMOTE_HEAD="$moved_head" "$r640_remote"
output "expected remote HEAD $MOCK_HEAD"
no_activation
run 1 env MOCK_BRANCH=topic "$r640_remote"
output 'expected branch main'
no_activation
run 1 env MOCK_DIRTY=' M flake.nix' "$r640_remote"
output 'checkout is dirty'
no_activation
run 98 env MOCK_GIT_STATUS_FAILURE=1 "$r640_remote"
no_activation
run 1 env MOCK_REMOTE_HOST=wrong "$r640_remote"
output 'host must be r640-0'
no_activation
run 1 env MOCK_FLAKE_HOST=wrong "$r640_remote"
output "flake output r640-0 declares hostname 'wrong'"
no_activation
run 1 env MOCK_NO_MOUNT=1 "$r640_remote"
output 'is not mounted'
no_activation
run 1 env MOCK_NO_POOL=1 "$r640_remote"
output 'ZFS pool mypool is unavailable'
no_activation
rmdir "$MOCK_PRIMARY/mypool/docker_data"
run 1 "$r640_remote"
output 'are not present'
no_activation
mkdir "$MOCK_PRIMARY/mypool/docker_data"

r640_pin="git+file://$MOCK_PRIMARY?rev=$MOCK_HEAD"
run 0 "$r640_remote" --check
called 'ssh<r640-0>'
called "nix<eval><--raw><$r640_pin#nixosConfigurations.r640-0.config.networking.hostName>"
grep -Fq "nix<eval><--json><$r640_pin#nixosConfigurations.r640-0.config.environment.systemPackages>" "$MOCK_CALLS"
output "$MOCK_HEAD"
no_activation
run 0 "$r640_remote" --dry-run
called 'ssh<r640-0>'
called "nix<build><--no-link><$r640_pin#nixosConfigurations.r640-0.config.system.build.toplevel>"
no_activation
run 0 env MOCK_MOVED_HEAD="$moved_head" "$r640_remote"
called 'ssh<-t><r640-0>'
called 'sudo<-v>'
called "sudo<nixos-rebuild><switch><--flake><$r640_pin#r640-0>"
grep -Fxq "head=$MOCK_HEAD" "$MOCK_ROLLBACK"
grep -Fxq "flake=$r640_pin#r640-0" "$MOCK_ROLLBACK"
grep -Fxq "rollback_command=sudo nixos-rebuild switch --rollback --flake $MOCK_PRIMARY#r640-0" "$MOCK_ROLLBACK"
output 'Switch completed'
run 1 env MOCK_CODEX_VERSION=0.0.0 "$r640_remote"
output 'activated Codex is 0.0.0, expected 1.2.3'

run 0 env MOCK_HOST=r640-0 MOCK_MOVED_HEAD="$moved_head" "$r640"
called "sudo<nixos-rebuild><switch><--flake><$MOCK_PRIMARY#r640-0>"
grep -Fxq "head=$moved_head" "$MOCK_ROLLBACK"

printf 'Machine switch contract checks passed.\n'
