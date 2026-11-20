#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workflow="$repo_root/.github/workflows/ci-build-images.yml"
test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT

group_template=$(yq -r '.concurrency.group' "$workflow")
cancel_in_progress=$(yq -r '.concurrency["cancel-in-progress"]' "$workflow")
# shellcheck disable=SC2016
[[ "$group_template" == 'ci-image-build-${{ github.repository }}' ]]
[[ "$cancel_in_progress" == false ]]

repository=pbert5/example
sha_a=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
sha_b=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
[[ "$sha_a" != "$sha_b" ]]

artifact_a="/ci/$repository/$sha_a/service:sha-$sha_a"
artifact_b="/ci/$repository/$sha_b/service:sha-$sha_b"
cache_ref="/buildkit/$repository/service:trusted-main"
[[ "$artifact_a" != "$artifact_b" ]]
[[ "$cache_ref" == "/buildkit/$repository/service:trusted-main" ]]

# Model the GitHub concurrency group with a lock: two source revisions use the
# same group lock while updating the same mutable cache ref.
lock_file="$test_root/ci-image-build-pbert5_example.lock"
active_file="$test_root/active"
timeline="$test_root/timeline"
printf '0\n' > "$active_file"
worker() {
  local source_sha=$1
  (
    flock -x 9
    [[ "$(cat "$active_file")" == 0 ]]
    printf '1\n' > "$active_file"
    printf 'start %s %s\n' "$source_sha" "$cache_ref" >> "$timeline"
    sleep 0.05
    printf '0\n' > "$active_file"
    printf 'end %s\n' "$source_sha" >> "$timeline"
  ) 9>"$lock_file"
}
worker "$sha_a" &
pid_a=$!
worker "$sha_b" &
pid_b=$!
wait "$pid_a"
wait "$pid_b"

[[ $(wc -l < "$timeline") -eq 4 ]]
[[ $(rg -c '^start ' "$timeline") -eq 2 ]]
[[ $(rg -c '^end ' "$timeline") -eq 2 ]]
[[ "$(cat "$active_file")" == 0 ]]
printf 'different source SHAs share a serialized cache-writer group and retain distinct artifact tags\n'
