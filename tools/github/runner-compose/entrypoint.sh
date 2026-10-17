#!/usr/bin/env bash
set -euo pipefail

state=/runner
if [[ ${1:-} == enroll ]]; then
  IFS= read -r token || { echo 'registration token missing on stdin' >&2; exit 2; }
  [[ -n $token ]] || { echo 'registration token is empty' >&2; exit 2; }
  repo=${RUNNER_REPOSITORY:?repository configuration missing}
  name=${RUNNER_NAME:?runner name missing}
  labels=${RUNNER_LABELS:?runner labels missing}
  mkdir -p "$state"
  cd "$state"
  # config.sh consumes the short-lived token; it is not written to disk or env.
  /opt/actions-runner/config.sh --unattended --url "https://github.com/$repo" \
    --token "$token" --name "$name" --labels "$labels" --work _work --replace --disableupdate
  unset token
  exit 0
fi

[[ -f "$state/.runner" && -f "$state/.credentials" ]] || {
  echo 'runner not enrolled; run ./tools/github/runners enroll' >&2
  exit 3
}
cd "$state"
exec /opt/actions-runner/run.sh
