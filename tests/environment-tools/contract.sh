#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)
fixture=$(mktemp -d)
trap 'rm -rf -- "$fixture"' EXIT
fixture=$(cd -P -- "$fixture" && pwd)
checkout="$fixture/fixture checkout"
foreign="$fixture/caller checkout"
git_local_vars=$(git rev-parse --local-env-vars)
while IFS= read -r name; do
  unset "$name"
done <<< "$git_local_vars"
unset CODEX_SHARED_RESOURCES CODEX_SHARED_RESOURCE_OWNER GIT_UPDATE_EXIT NIX_EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null GIT_ALLOW_PROTOCOL=file
export GIT_AUTHOR_NAME=Fixture GIT_AUTHOR_EMAIL=fixture@example.test
export GIT_COMMITTER_NAME=$GIT_AUTHOR_NAME GIT_COMMITTER_EMAIL=$GIT_AUTHOR_EMAIL

make_repo() {
  git init -q "$1"
  git -C "$1" commit -q --allow-empty -m fixture
}

make_repo "$fixture/leaf"
make_repo "$fixture/component"
git -C "$fixture/component" submodule add -q -- "$fixture/leaf" 'nested child'
git -C "$fixture/component" commit -q -m 'declare nested submodule'
make_repo "$foreign"
make_repo "$checkout"
git -C "$checkout" submodule add -q -- "$fixture/component" 'components/direct child'
git -C "$checkout" commit -q -m 'declare direct submodule'
git -C "$checkout" submodule deinit -q -- 'components/direct child'
git -C "$checkout" config submodule.recurse true
mkdir -p "$checkout/tools" "$checkout/scripts" "$fixture/bin"
cp -R -- "$root/tools/env" "$checkout/tools/"
cp -- "$root/scripts/codex-preflight" "$checkout/scripts/"
cp -- "$root/AGENTS.md" "$checkout/"
printf '{}\n' > "$checkout/flake.nix"
git -C "$checkout" add .
git -C "$checkout" commit -q -m 'declare direct submodule and environment tools'

REAL_GIT=$(command -v git)
export REAL_GIT
export NIX_CALL="$fixture/nix-call"
export PATH="$fixture/bin:$PATH"
cat > "$fixture/bin/git" <<'STUB'
#!/usr/bin/env bash
if [[ ${GIT_UPDATE_EXIT:-0} != 0 && " $* " == *' submodule update '* ]]; then
  exit "$GIT_UPDATE_EXIT"
fi
exec "$REAL_GIT" "$@"
STUB
cat > "$fixture/bin/nix" <<'STUB'
#!/usr/bin/env bash
printf '%s\0' "$PWD" "$@" > "$NIX_CALL"
exit "${NIX_EXIT:-0}"
STUB
cat > "$fixture/bin/gh" <<'STUB'
#!/usr/bin/env bash
exit 1
STUB
cp -- "$fixture/bin/gh" "$fixture/bin/codex"
chmod +x "$fixture/bin/"*

fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
expect_exit() {
  local want=$1 actual=0
  shift
  "$@" || actual=$?
  [[ $actual == "$want" ]] || fail "expected exit $want, got $actual from $*"
}
expect_nix() {
  printf '%s\0' "$checkout" "$@" > "$fixture/expected-nix-call"
  cmp -s "$fixture/expected-nix-call" "$NIX_CALL" || fail "wrong Nix cwd or arguments for $*"
  rm -- "$NIX_CALL"
}

cd -- "$foreign"
setup="$checkout/tools/env/setup"
shell="$checkout/tools/env/shell"
[[ -x $setup && -x $shell ]] || fail 'environment commands must be executable'
"$setup" --help >/dev/null
"$shell" --help >/dev/null
expect_exit 2 "$setup" --unknown >/dev/null 2>&1
expect_exit 2 "$setup" --status --check-flake >/dev/null 2>&1
expect_exit 2 "$shell" -- >/dev/null 2>&1
expect_exit 2 "$shell" --check extra >/dev/null 2>&1
[[ ! -e $NIX_CALL ]] || fail 'help or invalid arguments invoked Nix'

touch -t 200001010000 "$checkout/flake.nix"
cp -- "$checkout/.git/index" "$fixture/index-before"
cp -- "$checkout/.git/config" "$fixture/config-before"
status=$(GIT_DIR="$foreign/.git" GIT_WORK_TREE="$foreign" "$setup" --status --json)
jq -e --arg repo "$checkout" '
  .classification == "READY_WITH_RECOMMENDATIONS" and
  any(.checks[]; .name == "repo" and .detail == $repo) and
  any(.checks[]; .name == "submodules" and .state == "RECOMMENDATION")
' <<< "$status" > /dev/null || fail 'status must inspect the checkout containing the command'
cmp -s "$fixture/index-before" "$checkout/.git/index" || fail 'status rewrote the Git index'
cmp -s "$fixture/config-before" "$checkout/.git/config" || fail 'status modified Git config'
[[ ! -e "$checkout/components/direct child/.git" && ! -e $NIX_CALL ]] || fail 'status initialized a submodule or invoked Nix'

mv -- "$checkout/flake.nix" "$fixture/flake.nix"
expect_exit 1 "$setup" --status --json > "$fixture/status"
jq -e '.classification == "NOT_READY" and any(.checks[]; .name == "flake" and .state == "NOT_READY")' "$fixture/status" > /dev/null
expect_exit 1 "$setup" 2> /dev/null
expect_exit 1 "$shell" --check 2> /dev/null
[[ ! -e "$checkout/components/direct child/.git" && ! -e $NIX_CALL ]] || fail 'missing flake did not stop setup and shell'
mv -- "$fixture/flake.nix" "$checkout/flake.nix"

GIT_UPDATE_EXIT=31 expect_exit 31 "$setup"
[[ ! -e $NIX_CALL ]] || fail 'setup invoked Nix after Git failed'
GIT_DIR="$foreign/.git" GIT_WORK_TREE="$foreign" "$setup"
[[ -e "$checkout/components/direct child/.git" ]] || fail 'setup did not initialize the direct submodule'
[[ ! -e "$checkout/components/direct child/nested child/.git" ]] || fail 'setup initialized a nested submodule'
expect_nix print-dev-env --no-update-lock-file --json .
NIX_EXIT=37 expect_exit 37 "$setup"
expect_nix print-dev-env --no-update-lock-file --json .

"$shell"
expect_nix develop --no-update-lock-file .
"$shell" --check
expect_nix print-dev-env --no-update-lock-file --json .
NIX_EXIT=39 expect_exit 39 "$shell" -- printf '%s' 'two words' '' --check
expect_nix develop --no-update-lock-file . --command printf '%s' 'two words' '' --check
printf 'Environment tools contract checks passed.\n'
