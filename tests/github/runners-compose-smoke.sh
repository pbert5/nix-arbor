#!/usr/bin/env bash
set -euo pipefail

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd -P)
tmp=$(mktemp -d)
project="nix-arbor-runner-smoke-$(basename "$tmp" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')"
created=0
compose_file="$root/tools/github/runner-compose/compose.yaml"
env_file="$tmp/runner.env"
override="$tmp/override.yaml"

cleanup() {
  if ((created)); then
    docker compose --project-name "$project" --env-file "$env_file" \
      -f "$compose_file" -f "$override" down -v >/dev/null 2>&1 || true
  fi
  rm -rf -- "$tmp"
}
trap cleanup EXIT

cat >"$env_file" <<'ENV'
RUNNER_REPOSITORY=pbert5/meta_bal
RUNNER_NAME=disposable-smoke
RUNNER_LABELS=r640-0,meta-bal,docker-compose
RUNNER_VERSION=2.338.0
RUNNER_SHA256=af4b794c1bc41d73d40535e3fe092a39f9679cd8d965954c2aca25a05ca41d32
ENV
cat >"$override" <<'YAML'
services:
  runner:
    entrypoint: ["/bin/sh", "-c"]
    command: ["test -f /runner/.runner || printf 'disposable-runner-id\\n' > /runner/.runner; test -f /runner/.credentials || touch /runner/.credentials; exec sleep 3600"]
YAML

compose() {
  docker compose --project-name "$project" --env-file "$env_file" \
    -f "$compose_file" -f "$override" "$@"
}

if [[ -n $(docker ps -aq --filter "label=com.docker.compose.project=$project") || \
      -n $(docker volume ls -q --filter "label=com.docker.compose.project=$project") || \
      -n $(docker network ls -q --filter "label=com.docker.compose.project=$project") ]]; then
  echo "refusing to reuse existing Docker project name: $project" >&2
  exit 1
fi
compose config --quiet
created=1
compose up -d runner
container=$(compose ps -q runner)
[[ -n $container ]]
first_container=$container
sleep 2
if [[ $(docker inspect --format '{{.State.Status}}' "$container") != running ]]; then
  docker inspect --format 'state={{.State.Status}} exit={{.State.ExitCode}} error={{.State.Error}} args={{json .Config.Cmd}} entrypoint={{json .Config.Entrypoint}}' "$container" >&2
  docker logs "$container" >&2
  echo 'disposable runner container did not remain running' >&2
  exit 1
fi
docker exec "$container" test -s /runner/.runner
docker exec "$container" test -f /runner/.credentials
[[ $(docker exec "$container" id -u) == 1001 ]]
docker exec "$container" sh -c "printf 'persisted-runner-id\\n' > /runner/.runner; printf 'persisted-credential-marker\\n' > /runner/.credentials"
compose up -d --force-recreate runner
container=$(compose ps -q runner)
[[ -n $container && $container != "$first_container" ]]
[[ $(docker exec "$container" cat /runner/.runner) == persisted-runner-id ]]
[[ $(docker exec "$container" cat /runner/.credentials) == persisted-credential-marker ]]
compose restart runner
container=$(compose ps -q runner)
[[ $(docker exec "$container" cat /runner/.runner) == persisted-runner-id ]]
[[ $(docker exec "$container" cat /runner/.credentials) == persisted-credential-marker ]]
printf 'Disposable Compose restart and named-volume persistence passed (%s).\n' "$project"
