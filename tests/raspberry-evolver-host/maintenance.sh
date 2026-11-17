#!/usr/bin/env bash
set -euo pipefail
# Exercise the pinned nix-env age policy in an explicit disposable local store.
# nix-collect-garbage delegates per-profile deletion to this operation; avoid
# invoking its host-wide profile discovery in a test.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
store="local?root=$tmp/root"
profile="$tmp/root/nix/var/nix/profiles/system"
mkdir -p "${profile%/*}" "$tmp/root/nix/var/nix/gcroots"
nix-store --store "$store" --init
for n in 1 2 3 4 5; do
  printf 'generation %s\n' "$n" > "$tmp/input-$n"
  path=$(nix-store --store "$store" --add "$tmp/input-$n")
  printf '%s\n' "$path" > "$tmp/path-$n"
  ln -s "$path" "$profile-$n-link"
done
printf 'unreferenced\n' > "$tmp/unreferenced"
unreferenced=$(nix-store --store "$store" --add "$tmp/unreferenced")
ln -s system-5-link "$profile"
touch -h -d '30 days ago' "$profile"-{1,2,3}-link
touch -h -d '7 days ago' "$profile-4-link"
ln -s "$(cat "$tmp/path-1")" "$tmp/root/nix/var/nix/gcroots/booted-system"
ln -s "$(cat "$tmp/path-2")" "$tmp/root/nix/var/nix/gcroots/independent-pin"
ln -s "$(cat "$tmp/path-5")" "$tmp/root/nix/var/nix/gcroots/current-system"
nix-env --store "$store" --profile "$profile" --delete-generations 14d
for n in 1 2; do test ! -L "$profile-$n-link"; done
for n in 3 4 5; do test -L "$profile-$n-link"; done
nix-store --store "$store" --gc
for n in 1 2 3 4 5; do nix path-info --store "$store" "$(cat "$tmp/path-$n")" >/dev/null; done
if nix path-info --store "$store" "$unreferenced" >/dev/null 2>&1; then exit 1; fi
printf '%s\n' 'age selection and root retention: PASS'
