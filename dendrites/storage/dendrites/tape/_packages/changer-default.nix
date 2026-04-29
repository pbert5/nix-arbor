{ pkgs }:

pkgs.writeShellApplication {
  name = "changer-default";
  text = ''
    set -eu

    for candidate in /dev/tape/by-id/REPLACE_ME
      if [ -e "$candidate" ]; then
        printf '%s\n' "$candidate"
        exit 0
      fi
    done

    echo "No default tape changer found." >&2
    exit 1
  '';
}
