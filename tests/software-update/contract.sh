#!/usr/bin/env bash
set -euo pipefail

source_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
checkout="$scratch/fixture checkout"
export checkout
export log="$scratch/calls"
export old_codex=1111111111111111111111111111111111111111
export old_host=2222222222222222222222222222222222222222
export old_editor=3333333333333333333333333333333333333333
export revision=4444444444444444444444444444444444444444
export discovered_revision=$revision

fail() { printf 'software-update fixture: %s\n' "$*" >&2; exit 1; }
require() { rg -q -- "$1" "$2" || fail "missing '$1' in $2"; }
reject() {
  if "$@" >"$scratch/output" 2>&1; then
    fail "unexpected success: $*"
  fi
}
clean() { [[ -z $(git -C "$checkout" status --porcelain) ]] || fail 'fixture checkout changed'; }

mkdir -p "$checkout/tools/software/update" "$checkout/tools/machines/"{r640-0,evolver} "$scratch/bin"
cp "$source_root/tools/software/update/"* "$checkout/tools/software/update/"
jq --arg codex "$old_codex" --arg host "$old_host" --arg editor "$old_editor" '
  .nodes[.nodes[.root].inputs["codex-nixpkgs"]].original.rev = $codex
  | .nodes[.nodes[.root].inputs["codex-nixpkgs"]].locked.rev = $codex
  | .nodes[.nodes[.root].inputs.nixpkgs].locked.rev = $host
  | .nodes[.nodes[.nodes[.root].inputs["ashes-desktop-apps"]].inputs["nixpkgs-unstable"]].locked.rev = $editor
' "$source_root/flake.lock" >"$checkout/flake.lock"
sed -E "/codex-nixpkgs\.url/ s|/[0-9a-f]{40}|/$old_codex|" "$source_root/flake.nix" >"$checkout/flake.nix"
printf 'result-*\n' >"$checkout/.gitignore"
printf 'unrelated\n' >"$checkout/keep"
touch "$log"

for machine in r640-0 evolver; do
  cat >"$checkout/tools/machines/$machine/switch" <<'SWITCH'
#!/usr/bin/env bash
set -eu
[[ $# == 0 ]]
printf 'machine %s\n' "$(basename "$(dirname "$0")")" >>"$log"
if [[ -n ${expected_switch_rev:-} ]]; then
  jq -e --arg rev "$expected_switch_rev" \
    '.nodes[.nodes[.root].inputs.nixpkgs].locked.rev == $rev' "$checkout/flake.lock" >/dev/null
fi
if [[ ${switch_failure:-} == yes ]]; then exit 9; fi
SWITCH
  chmod +x "$checkout/tools/machines/$machine/switch"
done

cat >"$scratch/bin/hostname" <<'HOSTNAME'
#!/usr/bin/env bash
set -eu
[[ $1 == -s ]]
printf '%s\n' "${running_host:-r640-0}"
HOSTNAME
cat >"$scratch/bin/curl" <<'CURL'
#!/usr/bin/env bash
set -eu
[[ ${!#} == 'https://api.github.com/repos/NixOS/nixpkgs/commits?sha=master&path=pkgs/by-name/co/codex/package.nix&per_page=1' ]]
jq -n --arg rev "$discovered_revision" '[{sha: $rev}]'
CURL
export fixture_real_mv
fixture_real_mv=$(command -v mv)
cat >"$scratch/bin/mv" <<'MV'
#!/usr/bin/env bash
set -eu
if [[ ${replace_failure:-} == yes && $3 == */after/flake.lock ]]; then
  if [[ ${edit_after_first_replace:-} == yes ]]; then
    printf '\n# edit during publication\n' >>"$checkout/flake.nix"
  fi
  exit 12
fi
exec "$fixture_real_mv" "$@"
MV
cat >"$scratch/bin/nix" <<'NIX'
#!/usr/bin/env bash
set -eu
printf 'nix %s\n' "$*" >>"$log"
case "$1 $2" in
  'flake metadata')
    [[ $* == *'--no-update-lock-file'* ]]
    [[ ${metadata_failure:-} != yes ]] || exit 4
    if [[ ${concurrent_edit:-} == yes ]]; then
      printf '\n# concurrent edit\n' >>"$checkout/flake.lock"
    fi
    ref=${!#}
    fetched=${metadata_revision:-${ref##*/}}
    jq -n --arg rev "$fetched" '{
      locked: {type: "github", owner: "NixOS", repo: "nixpkgs", rev: $rev, narHash: "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=", lastModified: 42, __final: true},
      locks: {nodes:{root:{}},root:"root",version:7}
    }'
    ;;
  'eval --raw')
    case "$*" in
      *config.networking.hostName*)
        [[ $* == *'--no-update-lock-file'* ]]
        ref=${!#}
        target=${ref#*nixosConfigurations.}
        printf '%s' "${configured_host:-${target%%.*}}"
        ;;
      *config.nixpkgs.hostPlatform.system*) printf 'x86_64-linux' ;;
      *--expr*)
        [[ $* == *'config.allowUnfree = true'* && $* == *'.vscode'* ]]
        printf '%s' "${editor_version-1.133.0}"
        ;;
      *) exit 30 ;;
    esac
    ;;
  'eval --json')
    [[ $* == *'--no-update-lock-file'* && $* == *config.environment.systemPackages* ]]
    if [[ $4 == path:* ]]; then
      location=${4#path:}
      location=${location%%#*}
      rg -q "\"rev\": \"$revision\"" "$location/flake.lock"
      if [[ $* == *nixosConfigurations.r640-0* ]]; then
        rg -q "codex-nixpkgs\.url.*$revision" "$location/flake.nix"
      fi
    elif [[ -n ${current_codex_versions:-} ]]; then
      printf '%s\n' "$current_codex_versions"
      exit 0
    fi
    printf '%s\n' "${codex_versions:-[\"0.199.0\"]}"
    ;;
  'build --out-link')
    [[ $3 == "$checkout/result-vscode" && $* == *'config.allowUnfree = true'* ]]
    [[ ${build_failure:-} != yes ]] || exit 5
    ln -sfn "/nix/store/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-vscode-1.133.0" "$3"
    ;;
  *) exit 31 ;;
esac
NIX
chmod +x "$scratch/bin/"*
export PATH="$scratch/bin:$PATH"

git -C "$checkout" init -q -b main
git -C "$checkout" add .
git -C "$checkout" -c user.name=fixture -c user.email=fixture@example.invalid commit -qm fixture
cp "$checkout/flake.lock" "$scratch/original.lock"
cp "$checkout/flake.nix" "$scratch/original.nix"

codex="$checkout/tools/software/update/codex"
vscode="$checkout/tools/software/update/vscode"
cd -- "$scratch"

"$codex" --help >"$scratch/output"
require 'update --host' "$scratch/output"
"$vscode" --help >"$scratch/output"
require 'result-vscode/bin/code' "$scratch/output"
"$codex" preview --host r640-0 >"$scratch/output"
require "$old_codex" "$scratch/output"
"$vscode" preview --host desktoptoodle >"$scratch/output"
require 'ashes-desktop-apps/nixpkgs-unstable' "$scratch/output"
require "$old_editor" "$scratch/output"
"$codex" preview --host eVolver >"$scratch/output"
require 'allow-host-nixpkgs' "$scratch/output"
[[ ! -s $log ]] || fail 'help or preview invoked Nix or a switch'
clean

reject "$codex" update --host desktoptoodle --revision "$revision"
reject "$vscode" update --host nonexistent --revision "$revision"
reject "$codex" update --host r640-0 --revision nixos-unstable
reject "$codex" update --host r640-0 --revision "$revision" --switch
require 'clean main' "$scratch/output"
reject "$codex" update --host eVolver --revision "$revision"
require 'allow-host-nixpkgs' "$scratch/output"
reject "$codex" switch --host eVolver
[[ ! -s $log ]] || fail 'invalid requests invoked Nix or a switch'
clean
(
  exec {test_lock}<"$checkout/.git"
  flock -n "$test_lock"
  reject "$codex" update --host r640-0 --revision "$revision"
  require 'another software update or switch' "$scratch/output"
)
[[ ! -s $log ]] || fail 'the concurrent invocation reached Nix'

metadata_failure=yes reject "$codex" update --host r640-0 --revision "$revision"
metadata_revision="$old_codex" reject "$codex" update --host r640-0 --revision "$revision"
codex_versions='[""]' reject "$codex" update --host r640-0 --revision "$revision"
codex_versions='["0.100.0","0.200.0"]' reject "$codex" update --host r640-0 --revision "$revision"
configured_host=invalid reject "$codex" update --host r640-0 --revision "$revision"
editor_version='' running_host=desktoptoodle reject "$vscode" update --host desktoptoodle --revision "$revision" --switch
[[ ! -e $checkout/result-vscode && ! -L $checkout/result-vscode ]] || fail 'failed update created an editor link'
clean
if rg -q '^machine |^nix build ' "$log"; then fail 'failed update reached switch'; fi

printf '\n# existing edit\n' >>"$checkout/flake.nix"
cp "$checkout/flake.nix" "$scratch/edited.nix"
reject "$codex" update --host r640-0 --revision "$revision"
cmp "$checkout/flake.nix" "$scratch/edited.nix"
cmp "$checkout/flake.lock" "$scratch/original.lock"
cp "$scratch/original.nix" "$checkout/flake.nix"
for flag in assume-unchanged skip-worktree; do
  git -C "$checkout" update-index "--$flag" -- flake.nix
  printf '\n# edit hidden by %s\n' "$flag" >>"$checkout/flake.nix"
  cp "$checkout/flake.nix" "$scratch/edited.nix"
  clean
  reject "$codex" update --host r640-0 --revision "$revision"
  cmp "$checkout/flake.nix" "$scratch/edited.nix"
  cmp "$checkout/flake.lock" "$scratch/original.lock"
  cp "$scratch/original.nix" "$checkout/flake.nix"
  git -C "$checkout" update-index "--no-$flag" -- flake.nix
done
concurrent_edit=yes reject "$codex" update --host r640-0 --revision "$revision"
require '^# concurrent edit' "$checkout/flake.lock"
cmp "$checkout/flake.nix" "$scratch/original.nix"
cp "$scratch/original.lock" "$checkout/flake.lock"
clean
replace_failure=yes reject "$codex" update --host r640-0 --revision "$revision"
require 'could not replace flake.lock' "$scratch/output"
cmp "$checkout/flake.nix" "$scratch/original.nix"
cmp "$checkout/flake.lock" "$scratch/original.lock"
clean
replace_failure=yes edit_after_first_replace=yes reject "$codex" update --host r640-0 --revision "$revision"
require '^# edit during publication' "$checkout/flake.nix"
require 'recovery copies' "$scratch/output"
cmp "$checkout/flake.lock" "$scratch/original.lock"
for recovery in "$checkout"/.software-update.*; do
  cmp "$recovery/before/flake.nix" "$scratch/original.nix"
  find "$recovery" -depth -delete
done
cp "$scratch/original.nix" "$checkout/flake.nix"
clean

assert_scoped_lock() {
  local node=$1
  jq -e --arg node "$node" --arg revision "$revision"     '.nodes[$node].locked.rev == $revision' "$checkout/flake.lock" >/dev/null
  diff -u <(jq -S --arg node "$node" 'del(.nodes[$node])' "$scratch/original.lock")     <(jq -S --arg node "$node" 'del(.nodes[$node])' "$checkout/flake.lock")
}
restore() {
  cp "$scratch/original.lock" "$checkout/flake.lock"
  cp "$scratch/original.nix" "$checkout/flake.nix"
}

running_host=eVolver reject "$codex"
current_codex_versions='["0.200.0"]' "$codex" >"$scratch/output"
require 'already at' "$scratch/output"
clean
current_codex_versions='["0.198.0"]' "$codex" >"$scratch/output"
assert_scoped_lock codex-nixpkgs
if rg -q '^machine ' "$log"; then fail 'automatic update reached the machine wrapper'; fi
restore

printf 'preserve staged edit\n' >>"$checkout/keep"
git -C "$checkout" add keep
printf 'preserve working edit\n' >>"$checkout/keep"
"$codex" update --host r640-0 --revision "$revision" >"$scratch/output"
require '0.199.0' "$scratch/output"
require "codex-nixpkgs\.url.*$revision" "$checkout/flake.nix"
assert_scoped_lock codex-nixpkgs
jq -e --arg revision "$revision" '.nodes["codex-nixpkgs"].original.rev == $revision' "$checkout/flake.lock" >/dev/null
[[ $(git -C "$checkout" status --porcelain keep) == 'MM keep' ]]
git -C "$checkout" show :keep >"$scratch/indexed"
require 'preserve staged edit' "$scratch/indexed"
require 'preserve working edit' "$checkout/keep"
[[ $(git -C "$checkout" rev-list --count HEAD) == 1 ]]
"$codex" switch --host r640-0 >"$scratch/output"
require '^machine r640-0$' "$log"
restore

: >"$log"
running_host=eVolver metadata_failure=yes reject "$codex" update --host eVolver --revision "$revision" --allow-host-nixpkgs --switch
if rg -q '^machine ' "$log"; then fail 'failed host update reached the machine wrapper'; fi
running_host=eVolver expected_switch_rev="$revision" "$codex" update --host eVolver --revision "$revision" --allow-host-nixpkgs --switch >"$scratch/output"
require '0.199.0' "$scratch/output"
require '^machine evolver$' "$log"
assert_scoped_lock nixpkgs_5
cmp "$checkout/flake.nix" "$scratch/original.nix"
jq -e '.nodes.nixpkgs_5.original.ref == "nixos-unstable"' "$checkout/flake.lock" >/dev/null
restore
running_host=eVolver expected_switch_rev="$revision" switch_failure=yes reject \
  "$codex" update --host eVolver --revision "$revision" --allow-host-nixpkgs --switch
require 'Updated nixpkgs' "$scratch/output"
assert_scoped_lock nixpkgs_5
restore

mkdir "$checkout/result-vscode"
running_host=desktoptoodle reject "$vscode" switch --host desktoptoodle
[[ -d $checkout/result-vscode && ! -L $checkout/result-vscode ]]
rmdir "$checkout/result-vscode"
running_host=desktoptoodle "$vscode" update --host desktoptoodle --revision "$revision" --switch >"$scratch/output"
require '1.133.0' "$scratch/output"
require 'result-vscode/bin/code' "$scratch/output"
[[ -L $checkout/result-vscode ]]
assert_scoped_lock nixpkgs-unstable
cmp "$checkout/flake.nix" "$scratch/original.nix"
jq -e '.nodes["nixpkgs-unstable"].original.ref == "nixos-unstable"' "$checkout/flake.lock" >/dev/null
editor_link=$(readlink "$checkout/result-vscode")
running_host=desktoptoodle build_failure=yes reject "$vscode" switch --host desktoptoodle
[[ $(readlink "$checkout/result-vscode") == "$editor_link" ]]
assert_scoped_lock nixpkgs-unstable
printf 'software-update contract passed\n'
