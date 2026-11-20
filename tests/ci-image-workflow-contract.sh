#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT

caller_checkout="$test_root/caller-repo"
producer_checkout="$test_root/nix-arbor"
staged_contract="$test_root/runner-temp/ci-image-contract"
mkdir -p "$caller_checkout" "$producer_checkout/schemas" "$producer_checkout/scripts"
[[ ! -e "$caller_checkout/schemas" ]]

cp "$repo_root/scripts/stage-ci-image-contract.sh" "$producer_checkout/scripts/"
cp "$repo_root/schemas/ci-image-manifest-validation.jq" \
  "$repo_root/schemas/ci-image-evidence.jq" \
  "$repo_root/schemas/ci-image-manifest.schema.json" \
  "$producer_checkout/schemas/"
git -C "$producer_checkout" init -q
git -C "$producer_checkout" -c user.name=ContractTest -c user.email=contract@example.invalid \
  add scripts schemas
git -C "$producer_checkout" -c user.name=ContractTest -c user.email=contract@example.invalid \
  commit -qm 'producer-owned workflow contract fixture'
producer_sha=$(git -C "$producer_checkout" rev-parse HEAD)

bash "$producer_checkout/scripts/stage-ci-image-contract.sh" \
  "$producer_checkout" "$staged_contract" "$producer_sha"
for contract_file in \
  ci-image-manifest-validation.jq \
  ci-image-evidence.jq \
  ci-image-manifest.schema.json; do
  cmp "$repo_root/schemas/$contract_file" "$staged_contract/$contract_file"
done
cat > "$test_root/manifest.json" <<'EOF'
{"schemaVersion":1,"repository":"pbert5/example","images":[{"name":"service","context":".","dockerfile":"Dockerfile","platforms":["linux/amd64"],"buildArgs":{}}]}
EOF
jq -e --arg repo pbert5/example \
  --from-file "$staged_contract/ci-image-manifest-validation.jq" \
  "$test_root/manifest.json" >/dev/null
jq -n --arg repository pbert5/example --arg image service \
  --arg sourceSha "$producer_sha" --arg sourceTree fixture-tree \
  --arg manifestSha256 fixture-manifest --arg context . --arg dockerfile Dockerfile \
  --arg dockerfileSha256 fixture-dockerfile --arg platforms linux/amd64 \
  --arg cache registry/cache --arg reference registry/image:sha-fixture \
  --arg pullReference registry/image --arg digest "sha256:$(printf 'a%.0s' {1..64})" \
  --from-file "$staged_contract/ci-image-evidence.jq" > "$test_root/evidence.json"
jq -e '.repository == "pbert5/example" and .artifact.immutableReference == "registry/image@sha256:'"$(printf 'a%.0s' {1..64})"'"' "$test_root/evidence.json" >/dev/null

bad_stage="$test_root/runner-temp/wrong-sha"
bad_sha="0${producer_sha:1}"
if [[ "$bad_sha" == "$producer_sha" ]]; then bad_sha="1${producer_sha:1}"; fi
if bash "$producer_checkout/scripts/stage-ci-image-contract.sh" \
  "$producer_checkout" "$bad_stage" "$bad_sha"; then
  echo 'staging unexpectedly accepted a mismatched workflow SHA' >&2
  exit 1
fi
[[ ! -e "$bad_stage" ]]
[[ ! -e "$caller_checkout/schemas" ]]
printf 'caller checkout without schemas passed pinned producer-contract staging\n'
