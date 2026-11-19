set -euo pipefail
umask 077

release=/var/lib/raspberry-evolver/thin-release
checkout=$HOME/evolver
cd "$release"
sha256sum -c SHA256SUMS

[[ $(uname -m) == aarch64 ]]
revision=$(head -n 1 thin-images)
verify_images() {
  while read -r image digest; do
    [[ $(docker image inspect --format '{{.Id}}' "$image") == "$digest" ]] || return 1
  done < <(tail -n +2 "$release/thin-images")
}

# Publish the operator checkout only once it can start from verified images.
# If interrupted after publication, verify and clean up without modifying it.
if [[ -e $checkout || -L $checkout ]]; then
  [[ -d $checkout && ! -L $checkout ]]
  cmp "$release/thin-images" "$checkout/var/state/thin-images"
  verify_images
  exit
fi

candidate=$(mktemp -d "$HOME/.evolver.XXXXXX")
trap 'rm -rf -- "$candidate"' EXIT
git -C "$candidate" init --quiet
git -C "$candidate" fetch "$release/evolver.bundle" HEAD
git -C "$candidate" checkout -b pi-thin "$revision"
git -C "$candidate" remote add origin https://github.com/pbert5/simple-evolver.git
cd "$candidate"
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
verify_images
install -D -m 0600 "$release/thin-images" var/state/thin-images
mv -nT "$candidate" "$checkout"
[[ ! -e $candidate ]]
