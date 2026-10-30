#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <producer-checkout> <staging-directory> <expected-workflow-sha>" >&2
  exit 2
fi

producer_checkout=$1
staging_directory=$2
expected_sha=$3

[[ "$expected_sha" =~ ^[0-9a-f]{40}$ ]]
[[ -d "$producer_checkout" && ! -L "$producer_checkout" ]]
[[ ! -e "$staging_directory" && ! -L "$staging_directory" ]]
[[ "$staging_directory" != "$producer_checkout" && "$staging_directory" != "$producer_checkout"/* ]]
[[ "$(git -C "$producer_checkout" rev-parse HEAD)" == "$expected_sha" ]]

install -d -m 0700 "$staging_directory"
for contract_file in \
  ci-image-manifest-validation.jq \
  ci-image-evidence.jq \
  ci-image-manifest.schema.json; do
  source_file="$producer_checkout/schemas/$contract_file"
  [[ -f "$source_file" && ! -L "$source_file" ]]
  git -C "$producer_checkout" ls-files --error-unmatch "schemas/$contract_file" >/dev/null
  install -m 0444 "$source_file" "$staging_directory/$contract_file"
done
