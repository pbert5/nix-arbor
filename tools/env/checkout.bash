# shellcheck shell=bash
CDPATH= cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

# Git hooks can export repository-local variables for a different checkout.
git_local_vars=$(git rev-parse --local-env-vars)
while IFS= read -r name; do
  unset "$name"
done <<< "$git_local_vars"

if [[ $(git rev-parse --show-toplevel) != "$PWD" ]]; then
  printf 'Environment tools must run from a Git checkout containing tools/env.\n' >&2
  exit 1
fi

require_flake() {
  if [[ ! -f flake.nix ]]; then
    printf 'Missing flake.nix in %s\n' "$PWD" >&2
    exit 1
  fi
}
