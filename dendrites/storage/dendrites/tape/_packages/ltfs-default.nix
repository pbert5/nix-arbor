{ lib, pkgs, tapeDefault }:

pkgs.writeShellApplication {
  name = "ltfs-default";
  runtimeInputs = [
    pkgs.coreutils
    pkgs.gawk
    pkgs.lsscsi
  ];
  text = ''
    set -eu

    default_tape="${lib.getExe tapeDefault}"
    tape_device="$(readlink -f "$("$default_tape")")"

    case "$tape_device" in
      /dev/nst*)
        stream_device="/dev/''${tape_device#/dev/n}"
        ;;
      /dev/st*)
        stream_device="$tape_device"
        ;;
      *)
        stream_device="$tape_device"
        ;;
    esac

    ltfs_device="$(
      lsscsi -g | awk -v stream_device="$stream_device" '
        $2 == "tape" && $NF ~ /^\/dev\/sg[0-9]+$/ && $(NF - 1) == stream_device {
          print $NF
          exit
        }

        $2 == "tape" && $NF ~ /^\/dev\/sg[0-9]+$/ && fallback == "" {
          fallback = $NF
        }

        END {
          if (fallback != "") {
            print fallback
          }
        }
      '
    )"

    if [ -n "$ltfs_device" ]; then
      printf '%s\n' "$ltfs_device"
      exit 0
    fi

    echo "No default LTFS SCSI generic tape device found." >&2
    exit 1
  '';
}
