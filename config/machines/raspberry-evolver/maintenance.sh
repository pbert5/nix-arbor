#!/usr/bin/env bash
set -euo pipefail
exec 9>/run/lock/raspberry-evolver-maintenance.lock
flock -n 9 || exit 0
profile=/nix/var/nix/profiles/system
current=$(readlink -f /run/current-system)
booted=$(readlink -f /run/booted-system)
[ -n "$current" ] && [ -n "$booted" ] || exit 1
shopt -s nullglob
links=("$profile"-*-link)
((${#links[@]})) || exit 1
declare -A targets
current_gen= booted_gen=
for link in "${links[@]}"; do
  generation=${link#"$profile"-}; generation=${generation%-link}
  [[ $generation =~ ^[0-9]+$ ]] || exit 1
  target=$(readlink -f "$link") || exit 1
  [ -n "$target" ] && [ -z "${targets[$target]+x}" ] || exit 1
  targets[$target]=$generation
  [ "$target" != "$current" ] || current_gen=$generation
  [ "$target" != "$booted" ] || booted_gen=$generation
done
[ -n "$current_gen" ] && [ -n "$booted_gen" ] || exit 1
# Keep the current generation, booted generation and its two nearest predecessors.
mapfile -t prior < <(printf '%s\n' "${targets[@]}" | sort -rn | awk -v current="$current_gen" '$1 < current {print; if (++n == 2) exit}')
remove=()
for generation in "${targets[@]}"; do
  [ "$generation" != "$current_gen" ] || continue
  [ "$generation" != "$booted_gen" ] || continue
  [[ " ${prior[*]} " != *" $generation "* ]] || continue
  # Never delete newer generations, even after a rollback.
  (( generation < current_gen )) || continue
  remove+=("$generation")
done
if ((${#remove[@]})); then
  nix-env --profile "$profile" --delete-generations "${remove[@]}"
fi
nix-store --gc
