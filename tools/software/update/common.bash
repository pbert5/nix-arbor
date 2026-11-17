# Sourced by the checkout-local software update commands.

fail() { printf '%s update: %s\n' "$tool" "$*" >&2; exit 1; }
usage() {
  cat <<USAGE
Usage: tools/software/update/$tool preview --host HOST
       tools/software/update/$tool update --host HOST --revision NIXPKGS_SHA [--switch]
       tools/software/update/$tool switch --host HOST

Preview prints the checkout's current pin and scope. Update takes an explicit
40-digit hexadecimal Nixpkgs commit and evaluates the resulting package
version before writing the flake files. Switch requires the selected local
host. Update leaves the flake changes for review and commit.
USAGE
  if [[ $tool == codex ]]; then
    cat <<'USAGE'

Hosts: r640-0, eVolver
  r640-0 updates the exact codex-nixpkgs declaration and lock. After review and
  commit, run switch separately from the canonical clean main checkout.
  eVolver uses the shared host nixpkgs pin. Update requires --allow-host-nixpkgs
  because it can change other system packages and configurations.
  Switch uses the selected host's guarded NixOS system switch wrapper.
USAGE
  else
    cat <<'USAGE'

Hosts: r640-0, eVolver, desktoptoodle
  Update changes the nested AshDesktopApps unstable Nixpkgs pin, which is shared
  by the optional editor and other unstable desktop apps. Desktop core omits
  the editor. On r640-0 and eVolver the Remote-SSH module supplies compatibility
  libraries. The desktop client supplies the remote runtime.
  Switch builds the checkout-local result-vscode/bin/code entry point.
USAGE
  fi
}

action=${1:-}
case "$action" in
  -h|--help|'') usage; exit 0 ;;
  preview|update|switch) shift ;;
  *) usage >&2; exit 2 ;;
esac
host=
revision=
activate=false
allow_host=false
while (( $# )); do
  case "$1" in
    --host) [[ -z $host && ${2:-} && $2 != --* ]] || fail 'provide one --host HOST'; host=$2; shift ;;
    --revision) [[ -z $revision && ${2:-} && $2 != --* ]] || fail 'provide one --revision NIXPKGS_SHA'; revision=$2; shift ;;
    --switch) activate=true ;;
    --allow-host-nixpkgs) allow_host=true ;;
    *) fail "unknown option $1" ;;
  esac
  shift
done

case "$tool:$host" in
  codex:r640-0)
    machine=r640-0
    input=codex-nixpkgs
    scope='Dedicated exact Codex pin in flake.nix and flake.lock.'
    ;;
  codex:eVolver)
    machine=evolver
    input=nixpkgs
    scope='Shared host Nixpkgs. Other packages and configurations can change. Update requires --allow-host-nixpkgs.'
    ;;
  vscode:r640-0|vscode:eVolver|vscode:desktoptoodle)
    input=ashes-desktop-apps/nixpkgs-unstable
    scope='AshDesktopApps unstable packages, including the optional VS Code editor. Switch builds checkout-local result-vscode/bin/code.'
    ;;
  *) fail "select a supported --host for $tool (see --help)" ;;
esac

if [[ $action == update ]]; then
  [[ $revision =~ ^[0-9a-fA-F]{40}$ ]] || fail 'update requires a full 40-digit hexadecimal --revision'
  revision=${revision,,}
  if [[ $input == nixpkgs ]]; then
    "$allow_host" || fail "$scope"
  elif "$allow_host"; then
    fail '--allow-host-nixpkgs applies only to eVolver Codex updates'
  fi
  if [[ $input == codex-nixpkgs ]] && "$activate"; then
    fail 'review and commit the pin, then run switch separately from the canonical clean main checkout'
  fi
else
  [[ -z $revision ]] && ! "$activate" && ! "$allow_host" || fail "$action accepts only --host HOST"
fi

repo_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
[[ $(git -C "$repo_root" rev-parse --show-toplevel) == "$repo_root" ]] || fail 'expected a Nix Arbor checkout'
if [[ $action != preview ]]; then
  # A per-worktree lock serializes these commands without leaving a file.
  git_dir=$(git -C "$repo_root" rev-parse --absolute-git-dir)
  exec {update_fd}<"$git_dir"
  flock -n "$update_fd" || fail 'another software update or switch is in progress'
fi
lock="$repo_root/flake.lock"
[[ -f $lock && ! -L $lock && -f $repo_root/flake.nix && ! -L $repo_root/flake.nix ]] || fail 'expected regular flake.nix and flake.lock files'
node=$(jq -er --arg input "$input" '
  .nodes as $nodes
  | (reduce ($input | split("/")[]) as $part (.root; $nodes[.].inputs[$part])) as $node
  | select(($node | type) == "string")
  | $nodes[$node] as $leaf
  | select(($leaf.inputs // {}) == {})
  | select([$nodes[] | (.inputs // {})[] | select(. == $node)] | length == 1)
  | select([$leaf.original, $leaf.locked] | all(.type == "github" and .owner == "NixOS" and .repo == "nixpkgs"))
  | $node' "$lock") || fail "expected a single Nixpkgs leaf at $input"
old_revision=$(jq -er --arg node "$node" '.nodes[$node].locked.rev | select(test("^[0-9a-f]{40}$"))' "$lock") ||
  fail "could not determine the locked revision of $input"
if [[ $input == codex-nixpkgs ]]; then
  declared=$(sed -nE 's|^[[:space:]]*codex-nixpkgs\.url = "github:NixOS/nixpkgs/([0-9a-f]{40})";[[:space:]]*$|\1|p' "$repo_root/flake.nix")
  [[ $declared == "$old_revision" ]] &&
    jq -e --arg node "$node" --arg rev "$old_revision" '.nodes[$node].original.rev == $rev' "$lock" >/dev/null ||
    fail 'the exact Codex declaration and lock disagree'
fi

printf '%s on %s\nInput: %s (%s)\n%s\n' "$tool" "$host" "$input" "$old_revision" "$scope"
[[ $action != preview ]] || exit 0

if [[ $action == switch ]] || "$activate"; then
  running_host=$(hostname -s)
  [[ $running_host == "$host" ]] || fail "switch requires local hostname $host, found $running_host"
  if [[ $tool == codex ]]; then
    switch_tool="$repo_root/tools/machines/$machine/switch"
    [[ -x $switch_tool ]] || fail "machine switch is unavailable at $switch_tool"
  fi
fi

eval_version() {
  local flake=$1 lock_file=$2 platform locked
  local config="$flake#nixosConfigurations.$host.config"
  local configured_host
  configured_host=$(nix eval --raw --no-update-lock-file "$config.networking.hostName") ||
    fail "unable to evaluate the configuration for $host"
  [[ $configured_host == "$host" ]] || fail "the configuration for $host declares hostname '$configured_host'"

  if [[ $tool == codex ]]; then
    version=$(nix eval --json --no-update-lock-file "$config.environment.systemPackages" \
      --apply 'ps: map (p: p.version or "") (builtins.filter (p: (p.pname or "") == "codex") ps)' |
      jq -er 'select(length == 1) | .[0]') || fail "expected exactly one Codex package in $host"
  else
    platform=$(nix eval --raw --no-update-lock-file "$config.nixpkgs.hostPlatform.system") ||
      fail "unable to evaluate the platform for $host"
    [[ $platform =~ ^[a-zA-Z0-9_]+-[a-zA-Z0-9_]+$ ]] || fail "invalid platform for $host: $platform"
    locked=$(jq -er --arg node "$node" '
      .nodes[$node].locked | select(.rev | test("^[0-9a-f]{40}$"))
      | select(.narHash | test("^sha256-[A-Za-z0-9+/]{43}=$"))
      | "rev = \"\(.rev)\"; narHash = \"\(.narHash)\";"' "$lock_file") ||
      fail "invalid VS Code source in flake.lock"
    vscode_expr="(import (builtins.fetchTree { type = \"github\"; owner = \"NixOS\"; repo = \"nixpkgs\"; $locked }) { system = \"$platform\"; config.allowUnfree = true; }).vscode"
    version=$(nix eval --raw --expr "($vscode_expr).version") || fail 'unable to evaluate the VS Code version'
  fi
  [[ $version =~ ^[0-9][a-zA-Z0-9.+_-]*$ ]] || fail "unable to determine the $tool package version"
  printf '%s package version: %s\n' "$tool" "$version"
}

if [[ $action == update ]]; then
  changes=$(git -C "$repo_root" status --porcelain -- flake.nix flake.lock)
  [[ -z $changes ]] || fail 'preserve the existing changes to flake.nix or flake.lock before updating'

  scratch=$(mktemp -d)
  trap 'find "$scratch" -depth -delete' EXIT
  mkdir "$scratch/before" "$scratch/candidate"
  before="$scratch/before"
  candidate="$scratch/candidate"
  cp -- "$repo_root/flake.nix" "$lock" "$before/"
  git -C "$repo_root" ls-files --cached -z |
    tar -C "$repo_root" --no-recursion --null -T - -cf - |
    tar -C "$candidate" -xf -
  cp -- "$before/flake.nix" "$before/flake.lock" "$candidate/"

  # Resolve only the requested immutable Nixpkgs leaf with Nix. Keep the
  # original branch selectors and every unrelated node in Arbor's graph.
  new_leaf=$(nix flake metadata --json --no-update-lock-file "github:NixOS/nixpkgs/$revision" |
    jq -ce --arg rev "$revision" '
      select(.locks.nodes == {(.locks.root): {}})
      | .locked
      | select(.type == "github" and .owner == "NixOS" and .repo == "nixpkgs" and .rev == $rev)
      | select(.narHash | test("^sha256-[A-Za-z0-9+/]{43}=$"))
      | select(.lastModified | type == "number")
      | del(.__final)') || fail "unable to lock the requested Nixpkgs revision $revision"

  jq --arg node "$node" --arg input "$input" --arg revision "$revision" --argjson leaf "$new_leaf" '
    .nodes[$node].locked = $leaf
    | if $input == "codex-nixpkgs" then .nodes[$node].original.rev = $revision else . end
  ' "$before/flake.lock" >"$candidate/flake.lock"
  if [[ $input == codex-nixpkgs ]]; then
    sed -i "/^[[:space:]]*codex-nixpkgs\.url = / s|$old_revision|$revision|" "$candidate/flake.nix"
  fi
  eval_version "path:$candidate" "$candidate/flake.lock"

  # Manual edits can still occur while Nix evaluates the candidate.
  changes=$(git -C "$repo_root" status --porcelain -- flake.nix flake.lock)
  [[ -z $changes ]] && cmp -s "$repo_root/flake.nix" "$before/flake.nix" && cmp -s "$lock" "$before/flake.lock" ||
    fail 'flake files changed during evaluation; preserve those changes and try again'
  # git apply checks every path before applying the patch to the worktree.
  for file in flake.nix flake.lock; do
    diff -u --label "a/$file" --label "b/$file" "$before/$file" "$candidate/$file" || [[ $? == 1 ]]
  done >"$scratch/flakes.patch"
  if [[ -s $scratch/flakes.patch ]]; then
    git -C "$repo_root" apply --whitespace=nowarn "$scratch/flakes.patch" || fail 'unable to apply the verified flake update'
    printf 'Updated %s to %s. Review with git diff -- flake.nix flake.lock.\n' "$input" "$revision"
  else
    printf '%s is already locked to %s.\n' "$input" "$revision"
  fi
else
  eval_version "$repo_root" "$lock"
fi

if [[ $action == switch ]] || "$activate"; then
  if [[ $tool == codex ]]; then
    "$switch_tool"
  else
    link="$repo_root/result-vscode"
    if [[ -e $link || -L $link ]]; then
      [[ -L $link && $(readlink -- "$link") == /nix/store/*-vscode-* ]] ||
        fail "preserve the existing path at $link before switching"
    fi
    nix build --out-link "$link" --expr "$vscode_expr" || fail 'unable to build the VS Code entry point'
    printf 'VS Code entry point: %s/bin/code\n' "$link"
  fi
fi
