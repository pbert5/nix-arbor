set -euo pipefail
umask 077

release=/var/lib/raspberry-evolver/thin-release
checkout=$HOME/evolver
cd "$release"
sha256sum -c SHA256SUMS

[[ $(uname -m) == aarch64 ]]
revision=$(head -n 1 thin-images)
if [[ ! -e $checkout && ! -L $checkout ]]; then
  candidate=$(mktemp -d "$HOME/.evolver.XXXXXX")
  trap 'rm -rf -- "$candidate"' EXIT
  git -C "$candidate" init --quiet
  git -C "$candidate" fetch "$release/evolver.bundle" HEAD
  git -C "$candidate" checkout -b pi-thin "$revision"
  git -C "$candidate" remote add origin https://github.com/pbert5/simple-evolver.git
  mv -nT "$candidate" "$checkout"
fi
[[ -d $checkout && ! -L $checkout ]]
[[ $(git -C "$checkout" rev-parse HEAD) == "$revision" ]]

cd "$checkout"
if [[ ! -e .env && ! -L .env ]]; then
  temporary=$(mktemp .env.XXXXXX)
  {
    echo 'SIMPLE_EVOLVER_THIN_DISCOVERY=off'
    echo 'SIMPLE_EVOLVER_DATA_BIND=127.0.0.1'
    for role in POSTGRES GRAFANA_DB GRAFANA_ADMIN POSTGRES_METRICS MIGRATOR COMMAND_SUBMITTER \
      CONTROL_EXECUTOR SENSOR_ACQUIRER DATA_READER OBSERVER COORDINATION INVENTORY LIFECYCLE \
      CATALOG SCIENCE TELEMETRY ANALYTICS; do
      printf 'SIMPLE_EVOLVER_%s_PASSWORD=%s\n' "$role" "$(openssl rand -hex 32)"
    done
  } >"$temporary"
  mv -nT "$temporary" .env
  rm -f -- "$temporary"
fi
./tools/env secrets

gzip -dc "$release/images.tar.gz" | docker load
while read -r image digest; do
  [[ $(docker image inspect --format '{{.Id}}' "$image") == "$digest" ]]
done < <(tail -n +2 "$release/thin-images")
install -D -m 0600 "$release/thin-images" var/state/thin-images
