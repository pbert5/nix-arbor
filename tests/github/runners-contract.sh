#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd -P)
cli="$root/tools/github/runners"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/state"
export XDG_CONFIG_HOME="$tmp/config"
export MOCK_LOG="$tmp/docker.log"
export MOCK_STDIN="$tmp/docker.stdin"
export MOCK_STATE_FLAG="$tmp/state-present"
run_tty() { script -qefc "$*" /dev/null; }

cat >"$tmp/bin/docker" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$MOCK_LOG"
case "$*" in
  *"--user 1001:1001 --entrypoint /bin/sh runner -c test -w /runner"*)
    [[ ${MOCK_VOLUME_WRITABLE:-0} == 1 ]] || exit 10
    ;;
  *"--user 1001:1001 --entrypoint /bin/sh runner -c test -r /runner/.runner"*)
    [[ -f $MOCK_STATE_FLAG ]] || exit 11
    ;;
  *"--user 0:0 --entrypoint /bin/sh runner -c chown -R 1001:1001 /runner"*) ;;
  *"build runner"*) [[ ${MOCK_DOCKER_FAIL_BUILD:-0} == 1 ]] && exit 8 ;;
  *"run --rm -T --no-deps runner enroll"*)
    cat >"$MOCK_STDIN"
    [[ ${MOCK_DOCKER_FAIL_ENROLL:-0} == 1 ]] && exit 9
    : >"$MOCK_STATE_FLAG"
    ;;
esac
exit 0
MOCK
cat >"$tmp/bin/gh" <<'MOCK'
#!/usr/bin/env bash
if [[ $1 == auth && $2 == token ]]; then printf 'mock-long-lived-token\n'; exit 0; fi
if [[ $1 == auth && $2 == status ]]; then exit 0; fi
if [[ $1 == api ]]; then
  case "$*" in
    *"actions/runners/registration-token"*) printf 'mock-short-token\n' ;;
    *"repos/pbert5/meta_bal"*) printf 'pbert5/meta_bal\ttrue\tprivate\n' ;;
    *"repos/pbert5/simple-evolver"*) printf 'pbert5/simple-evolver\ttrue\tprivate\n' ;;
    *"repos/pbert5/meta-bal"*) printf 'pbert5/meta-bal\ttrue\tprivate\n' ;;
    *"repos/pbert5/failure"*) printf 'pbert5/failure\ttrue\tprivate\n' ;;
    *"repos/pbert5/buildfailure"*) printf 'pbert5/buildfailure\ttrue\tprivate\n' ;;
    *"repos/pbert5/nix-arbor"*) printf 'pbert5/nix-arbor\tfalse\tpublic\n' ;;
    *) exit 1 ;;
  esac
  exit 0
fi
exit 1
MOCK
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH"

if "$cli" enroll --repo pbert5/nix-arbor </dev/null >"$tmp/public.out" 2>&1; then
  echo 'public repository enrollment unexpectedly succeeded' >&2; exit 1
fi
grep -q 'only private repositories' "$tmp/public.out"

printf 'y\n\n\n' | run_tty "$cli enroll --repo pbert5/meta_bal" >"$tmp/enroll.out" || { cat "$tmp/enroll.out" >&2; exit 1; }
slug=$(printf 'pbert5/meta_bal' | sha256sum | cut -c1-8)
slug="pbert5-meta-bal-$slug"
conf="$XDG_CONFIG_HOME/nix-arbor/runners/$slug.conf"
[[ -f $conf && $(stat -c %a "$conf") == 600 ]]
grep -qx 'RUNNER_REPOSITORY=pbert5/meta_bal' "$conf"
grep -qx "RUNNER_LABELS=r640-0,$slug,docker-compose" "$conf"
grep -qx 'RUNNER_VERSION=2.338.0' "$conf"
grep -qx 'mock-short-token' "$MOCK_STDIN"
grep -q -- '--progress plain build runner' "$MOCK_LOG"
grep -q -- '--user 0:0 --entrypoint /bin/sh runner -c chown -R 1001:1001 /runner' "$MOCK_LOG"
if grep -q 'mock-short-token\|mock-long-lived-token' "$conf" "$tmp/enroll.out" "$MOCK_LOG"; then
  echo 'credential leaked to config, output, or Docker arguments' >&2; exit 1
fi

rm -f "$MOCK_STATE_FLAG"
if printf 'y\n\n\n' | run_tty "$cli enroll --repo pbert5/meta_bal" >"$tmp/repair.out"; then
  :
else
  cat "$tmp/repair.out" >&2; exit 1
fi
grep -q 'runner registration state is missing or unreadable; renewing enrollment' "$tmp/repair.out"
"$cli" enroll --repo pbert5/meta_bal >"$tmp/already.out"
grep -q 'Already configured' "$tmp/already.out"

: >"$MOCK_LOG"
export MOCK_VOLUME_WRITABLE=0
rm -f "$MOCK_STATE_FLAG"
if "$cli" up --repo pbert5/meta_bal >"$tmp/unregistered.out" 2>&1; then
  echo 'up unexpectedly started a runner without registration state' >&2; exit 1
fi
grep -q 'runner registration state is missing' "$tmp/unregistered.out"
if grep -q 'up -d runner' "$MOCK_LOG"; then
  echo 'up started the runner despite missing registration state' >&2; exit 1
fi
: >"$MOCK_STATE_FLAG"
: >"$MOCK_LOG"
"$cli" up --repo pbert5/meta_bal >/dev/null
grep -q -- '--user 0:0 --entrypoint /bin/sh runner -c chown -R 1001:1001 /runner' "$MOCK_LOG"
export MOCK_VOLUME_WRITABLE=1
"$cli" rebuild --repo pbert5/meta_bal >/dev/null
[[ $(grep -c 'up -d runner' "$MOCK_LOG") == 2 ]]
"$cli" up-up --repo pbert5/meta_bal >/dev/null
grep -q 'build --pull --no-cache runner' "$MOCK_LOG"
grep -q 'up -d --force-recreate runner' "$MOCK_LOG"
if grep -Eq 'down.*-v|volume prune|system prune' "$MOCK_LOG"; then
  echo 'runner command attempted destructive Docker cleanup' >&2; exit 1
fi
grep -q -- "--project-name nix-arbor-runner-$slug" "$MOCK_LOG"

: >"$MOCK_LOG"
for command_name in up rebuild up-up enroll down doctor; do
  guard_config="$tmp/guard-$command_name"
  if XDG_CONFIG_HOME="$guard_config" "$cli" "$command_name" --repo pbert5/simple-evolver >"$tmp/guard-$command_name.out" 2>&1; then
    echo "$command_name unexpectedly managed the transferred Simple Evolver runner" >&2; exit 1
  fi
  grep -q 'ownership has transferred to Simple Evolver' "$tmp/guard-$command_name.out" || {
    cat "$tmp/guard-$command_name.out" >&2
    echo "$command_name did not report the Simple Evolver ownership transfer" >&2
    exit 1
  }
  [[ ! -e $guard_config ]] || { echo "$command_name created Nix Arbor config for the transferred repo" >&2; exit 1; }
done
[[ ! -s $MOCK_LOG ]] || { echo 'a rejected command invoked Docker' >&2; cat "$MOCK_LOG" >&2; exit 1; }

default_config="$tmp/default-guard/nix-arbor/runners"
mkdir -p "$default_config"
simple_evolver_slug=$(printf 'pbert5/simple-evolver' | sha256sum | cut -c1-8)
simple_evolver_slug="pbert5-simple-evolver-$simple_evolver_slug"
printf 'RUNNER_REPOSITORY=pbert5/simple-evolver\n' >"$default_config/$simple_evolver_slug.conf"
if XDG_CONFIG_HOME="$tmp/default-guard" "$cli" up >"$tmp/default-guard.out" 2>&1; then
  echo 'implicit selection unexpectedly managed the transferred Simple Evolver runner' >&2; exit 1
fi
grep -q 'ownership has transferred to Simple Evolver' "$tmp/default-guard.out" || {
  cat "$tmp/default-guard.out" >&2
  echo 'implicit repository selection did not report the Simple Evolver ownership transfer' >&2
  exit 1
}
[[ ! -s $MOCK_LOG ]] || { echo 'implicit guard invocation ran Docker' >&2; cat "$MOCK_LOG" >&2; exit 1; }

simple_evolver_name="r640-0-$simple_evolver_slug"
printf 'RUNNER_REPOSITORY=pbert5/simple-evolver\nRUNNER_NAME=%s\nRUNNER_LABELS=r640-0,%s,docker-compose\nRUNNER_VERSION=2.338.0\nRUNNER_SHA256=fixture\n' \
  "$simple_evolver_name" "$simple_evolver_slug" >"$default_config/$simple_evolver_slug.conf"
: >"$MOCK_LOG"
XDG_CONFIG_HOME="$tmp/default-guard" "$cli" status --repo pbert5/simple-evolver >"$tmp/transferred-status.out"
grep -q 'GitHub repository policy: private' "$tmp/transferred-status.out"
grep -q 'compose .* ps$' "$MOCK_LOG"
if grep -Eq ' up -d| stop runner| build runner| run --rm' "$MOCK_LOG"; then
  echo 'transferred-repo status performed a mutating or ephemeral Compose operation' >&2; exit 1
fi

export MOCK_DOCKER_FAIL_ENROLL=1
if printf 'y\n\n\n' | run_tty "$cli enroll --repo pbert5/failure" >"$tmp/failure.out" 2>&1; then
  echo 'failed registration unexpectedly succeeded' >&2; exit 1
fi
grep -q 'registration failed' "$tmp/failure.out"
failure_slug=$(printf 'pbert5/failure' | sha256sum | cut -c1-8)
[[ ! -e "$XDG_CONFIG_HOME/nix-arbor/runners/pbert5-failure-$failure_slug.conf" ]]
unset MOCK_DOCKER_FAIL_ENROLL

export MOCK_DOCKER_FAIL_BUILD=1
if printf 'y\n\n\n' | run_tty "$cli enroll --repo pbert5/buildfailure" >"$tmp/buildfailure.out" 2>&1; then
  echo 'failed image build unexpectedly succeeded' >&2; exit 1
fi
grep -q 'runner image build failed' "$tmp/buildfailure.out"
buildfailure_slug=$(printf 'pbert5/buildfailure' | sha256sum | cut -c1-8)
[[ ! -e "$XDG_CONFIG_HOME/nix-arbor/runners/pbert5-buildfailure-$buildfailure_slug.conf" ]]
unset MOCK_DOCKER_FAIL_BUILD

if "$cli" up --repo 'pbert5/meta_bal;touch' >"$tmp/invalid.out" 2>&1; then
  echo 'invalid repository argument unexpectedly succeeded' >&2; exit 1
fi
printf 'GitHub runner tool contract checks passed.\n'
