{
  lib,
  pkgs,
  driveIndex ? 0,
  configuredDrives ? [ ],
}:

let
  configuredDriveArgs = lib.concatStringsSep " " (map lib.escapeShellArg configuredDrives);
in
pkgs.writeShellApplication {
  name = if driveIndex == 0 then "tape-default" else "tape-default-${toString (driveIndex + 1)}";
  runtimeInputs = [ pkgs.coreutils ];
  text = ''
        set -eu

        wanted_index=${toString driveIndex}
        configured_drives=( ${configuredDriveArgs} )

        if [ "''${#configured_drives[@]}" -gt 0 ]; then
          if [ "$wanted_index" -lt "''${#configured_drives[@]}" ]; then
            printf '%s\n' "''${configured_drives[$wanted_index]}"
            exit 0
          fi

          echo "No configured non-rewinding tape drive found for index $((wanted_index + 1))." >&2
          exit 1
        fi

        found_index=0
        seen_targets=""

        for candidate in /dev/tape/by-id/REPLACE_ME
          [ -e "$candidate" ] || continue

          target="$(readlink -f "$candidate" 2>/dev/null || printf '%s\n' "$candidate")"

          case "
    $seen_targets
    " in
            *"
    $target
    "*)
              continue
              ;;
          esac

          if [ "$found_index" -eq "$wanted_index" ]; then
            printf '%s\n' "$candidate"
            exit 0
          fi

          seen_targets="$seen_targets
    $target"
          found_index=$((found_index + 1))
        done

        echo "No default non-rewinding tape drive found for index $((wanted_index + 1))." >&2
        exit 1
  '';
}
