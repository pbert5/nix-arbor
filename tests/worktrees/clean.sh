#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
scratch=$(mktemp -d)
trap 'rm -rf -- "$scratch"' EXIT
local_git_vars=$(git rev-parse --local-env-vars)
while IFS= read -r variable; do
  unset "$variable"
done <<< "$local_git_vars"
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
export GIT_AUTHOR_NAME=Fixture GIT_AUTHOR_EMAIL=fixture@example.org
export GIT_COMMITTER_NAME=Fixture GIT_COMMITTER_EMAIL=fixture@example.org

repo="$scratch/arbor"
trees="$scratch/worktrees"
tool=tools/worktrees/clean

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

repo_git() { git -C "$repo" "$@"; }

add_tree() {
  repo_git worktree add -qb "agent/test/${1// /-}" "$trees/$1" "${2:-main}"
}

run() { ( cd "$scratch" && "$repo/$tool" "$@" ); }

expect_refusal() {
  local path=$1 reason=$2 output code=0
  output=$(run --apply "$path" 2>&1) || code=$?
  [[ $code == 1 && $output == *"$reason"* ]] || fail "apply $path returned $code: $output"
  [[ -d $path ]] || fail "apply removed $path"
}

git init -q -b main "$repo"
mkdir -p "$repo/tools/worktrees" "$trees"
[[ -x $root/$tool ]] || fail "missing executable $tool"
cp "$root/$tool" "$repo/$tool"
printf 'data\n' > "$repo/tracked"
printf '*.ignored\n' > "$repo/.gitignore"
printf 'tracked filter=fixture-clean\n' > "$repo/.gitattributes"
repo_git add tracked .gitignore .gitattributes "$tool"
repo_git commit -qm 'Start fixture'
repo_git remote add origin "$scratch/offline-origin"
repo_git update-ref refs/remotes/origin/main HEAD
repo_git switch -qc feature/source
repo_git commit -qm 'Advance a non-agent branch' --allow-empty
repo_git switch -q main
repo_git worktree add -q "$trees/non-agent" feature/source
repo_git switch -qc shared-history
repo_git commit -qm 'Shared branch reflog history' --allow-empty
repo_git reset -q HEAD^
repo_git switch -q main

add_tree 'clean path'
add_tree newline
newline_path=$trees/$'with\nnewline'
repo_git worktree move "$trees/newline" "$newline_path"
add_tree dirty
printf 'change\n' >> "$trees/dirty/tracked"
add_tree untracked
touch "$trees/untracked/new"
add_tree ignored
touch "$trees/ignored/local.ignored"
add_tree locked
repo_git worktree lock --reason 'test lock' "$trees/locked"
repo_git worktree add -q --detach "$trees/detached" main
add_tree unpublished
git -C "$trees/unpublished" commit -q --allow-empty -m 'Only local'
repo_git merge -q --ff-only agent/test/unpublished
add_tree current refs/remotes/origin/main
add_tree self refs/remotes/origin/main
add_tree local-ref refs/remotes/origin/main
git -C "$trees/local-ref" update-ref refs/worktree/test HEAD
add_tree reflog refs/remotes/origin/main
git -C "$trees/reflog" switch --detach -q
git -C "$trees/reflog" commit -qm 'Detached work to preserve' --allow-empty
detached_commit=$(git -C "$trees/reflog" rev-parse HEAD)
git -C "$trees/reflog" switch -q agent/test/reflog
git -C "$trees/reflog" reflog delete 'HEAD@{1}'
[[ $(git -C "$trees/reflog" reflog show --format=%H HEAD) != *"$detached_commit"* ]] ||
  fail 'detached commit should only be recorded as the previous tip'
[[ $(git -C "$trees/reflog" rev-list --single-worktree --reflog --no-walk) == *"$detached_commit"* ]] ||
  fail 'previous tip should resolve to the detached commit'
add_tree hidden-change refs/remotes/origin/main
git -C "$trees/hidden-change" update-index --assume-unchanged tracked
printf 'local edits\n' >> "$trees/hidden-change/tracked"

git init -q -b main "$scratch/component"
git -C "$scratch/component" commit -q --allow-empty -m 'Start component fixture'
repo_git -c protocol.file.allow=always submodule add -q "$scratch/component" component
repo_git commit -qm 'Add component'
repo_git update-ref refs/remotes/origin/main HEAD
add_tree submodule
git -C "$trees/submodule" -c protocol.file.allow=always submodule update -q --init
add_tree populated-gitlink
touch "$trees/populated-gitlink/component/local.ignored"
add_tree empty-submodule
add_tree unmerged
git -C "$trees/unmerged" commit -qm 'Not merged anywhere' --allow-empty
# Make this candidate published but unmerged into local main.
repo_git update-ref refs/remotes/origin/main agent/test/unmerged

add_tree filtered
export WORKTREE_FILTER_MARKER="$scratch/filter-ran"
filter_command="touch \"\$WORKTREE_FILTER_MARKER\"; cat"
repo_git config extensions.worktreeConfig true
repo_git config filter.unused.clean "$filter_command"
git -C "$trees/filtered" config --worktree filter.fixture-clean.clean "$filter_command"
touch -m -t 200001010000 "$trees/filtered/tracked"

# Keep a local main commit beyond origin/main to test unpublished separately.
repo_git commit -qm 'Ahead of origin' --allow-empty
add_tree local-only

before_trees=$(repo_git worktree list --porcelain)
before_refs=$(repo_git for-each-ref)
expect_refusal "$trees/reflog" reflog
preview=$(run)
[[ ! -e $WORKTREE_FILTER_MARKER ]] || fail 'preview executed a Git clean filter'
[[ $preview == "$(run --preview)" ]] || fail 'default mode differs from --preview'
[[ $preview == "$(GIT_DIR=$scratch/wrong.git GIT_INDEX_FILE=$scratch/wrong.index run)" ]] ||
  fail 'caller Git environment changed the preview'
[[ $preview == *"eligible $(printf '%q' "$trees/clean path")"* ]] ||
  fail "clean worktree missing from preview: $preview"
[[ $(repo_git worktree list --porcelain) == "$before_trees" ]] || fail 'preview changed worktrees'
[[ $(repo_git for-each-ref) == "$before_refs" ]] || fail 'preview changed refs'
[[ -d $trees/clean\ path ]] || fail 'preview removed eligible worktree'

for spec in 'dirty:changes' 'untracked:changes' 'ignored:ignored' 'locked:locked' 'detached:detached' \
    'non-agent:agent' 'local-only:origin/main' 'unmerged:local main' 'submodule:submodule' \
    'populated-gitlink:submodule' 'hidden-change:index flags' 'local-ref:worktree-local refs' \
    'filtered:external Git filter'; do
  expect_refusal "$trees/${spec%%:*}" "${spec#*:}"
done
expect_refusal "$repo" primary

mkdir "$trees/current/nested"
if ( cd "$trees/current/nested" && "$repo/$tool" --apply .. ); then fail 'removed the current worktree'; fi
[[ -d $trees/current ]] || fail 'current worktree is missing'
if ( cd "$scratch" && "$trees/self/$tool" --apply "$trees/self" ); then fail 'removed the tool checkout'; fi
[[ -d $trees/self ]] || fail 'tool checkout is missing'
if run --apply; then fail 'apply accepted no explicit path'; fi
if run --apply "$trees/clean path" "$trees/empty-submodule"; then fail 'apply accepted multiple paths'; fi
mkdir "$scratch/unregistered"
expect_refusal "$scratch/unregistered" 'registered worktree'
[[ $(repo_git worktree list --porcelain) == "$before_trees" ]] || fail 'refused apply changed worktrees'
[[ $(repo_git for-each-ref) == "$before_refs" ]] || fail 'refused apply changed refs'
[[ ! -e $WORKTREE_FILTER_MARKER ]] || fail 'apply executed a Git clean filter'

touch "$trees/clean path/new.ignored"
expect_refusal "$trees/clean path" ignored
rm "$trees/clean path/new.ignored"
run --apply 'worktrees/clean path'
run --apply "$trees/empty-submodule"
run --apply "$newline_path"
[[ ! -e $trees/clean\ path && ! -e $trees/empty-submodule && ! -e $newline_path ]] ||
  fail 'eligible worktree was not removed'
[[ $(repo_git for-each-ref) == "$before_refs" ]] || fail 'apply changed refs'
[[ $(repo_git worktree list --porcelain) != *'branch refs/heads/agent/test/clean-path'* ]] || fail 'apply left worktree registered'
repo_git remote remove origin
run --apply "$trees/local-only"
repo_git show-ref --verify --quiet refs/heads/agent/test/local-only || fail 'apply deleted local branch'
echo 'worktree cleanup fixtures passed'
