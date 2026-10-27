#!/usr/bin/env bash
set -euo pipefail

state=/runner
image_runner=/opt/actions-runner
install_marker="$state/.nix-arbor-runner-install"

prepare_runner_install() {
  local marker_value
  marker_value="${RUNNER_VERSION:?runner version missing}:${RUNNER_SHA256:?runner checksum missing}"
  if [[ ! -r $install_marker || $(<"$install_marker") != "$marker_value" ]]; then
    rsync -a --delete \
      --exclude='/.runner*' \
      --exclude='/.credentials*' \
      --exclude='/.service' \
      --exclude='/.env' \
      --exclude='/.path' \
      --exclude='/settings.json' \
      --exclude='/_work/' \
      --exclude='/_diag/' \
      --exclude='/.nix-arbor-*' \
      "$image_runner/" "$state/"
    printf '%s\n' "$marker_value" >"$install_marker"
  fi
}

prepare_runner_install
if [[ ${1:-} == prepare ]]; then
  exit 0
fi

if [[ ${1:-} == enroll ]]; then
  IFS= read -r token || { echo 'registration token missing on stdin' >&2; exit 2; }
  [[ -n $token ]] || { echo 'registration token is empty' >&2; exit 2; }
  repo=${RUNNER_REPOSITORY:?repository configuration missing}
  name=${RUNNER_NAME:?runner name missing}
  labels=${RUNNER_LABELS:?runner labels missing}
  mkdir -p "$state"
  cd "$state"
  # config.sh consumes the short-lived token; it is not written to disk or env.
  ./config.sh --unattended --url "https://github.com/$repo" \
    --token "$token" --name "$name" --labels "$labels" --work _work --replace --disableupdate
  unset token
  exit 0
fi

[[ -f "$state/.runner" && -f "$state/.credentials" ]] || {
  echo 'runner not enrolled; run ./tools/github/runners enroll' >&2
  exit 3
}
cd "$state"
exec ./run.sh
