{ pkgs }:
pkgs.runCommand "no-default-nix" { } ''
  set -eu

  repo=${../.}
  hits="$(${pkgs.findutils}/bin/find "$repo" \
    \( -path "$repo/.git" -o -path "$repo/experiments" -o -path "$repo/fruits/fossilsafe/FOSSILSAFE" \) -prune \
    -o -name default.nix -print)"

  if [ -n "$hits" ]; then
    echo "default.nix is forbidden in active repo-owned paths:" >&2
    echo "$hits" >&2
    exit 1
  fi

  touch "$out"
''
