{
  lib,
  pkgs,
  tapeDefault,
  name ? "mt",
}:

let
  wrappedMt = pkgs.writeShellApplication {
    inherit name;
    text = ''
      set -eu

      real_mt="${lib.getExe' pkgs.mt-st "mt"}"
      default_tape="${lib.getExe tapeDefault}"
      needs_device=1
      previous_was_flag=0

      for arg in "$@"; do
        if [ "$previous_was_flag" -eq 1 ]; then
          needs_device=0
          previous_was_flag=0
          continue
        fi

        case "$arg" in
          -f|-t)
            needs_device=0
            previous_was_flag=1
            ;;
          -f*|-t*)
            needs_device=0
            ;;
        esac
      done

      if [ "$needs_device" -eq 1 ]; then
        if [ -n "''${TAPE:-}" ]; then
          exec "$real_mt" -f "$TAPE" "$@"
        fi

        exec "$real_mt" -f "$("$default_tape")" "$@"
      fi

      exec "$real_mt" "$@"
    '';
  };
in
pkgs.symlinkJoin {
  name = "${name}-with-default-nst";
  paths = [
    pkgs.mt-st
    wrappedMt
  ];
  postBuild = ''
    rm "$out/bin/${name}"
    ln -s "${wrappedMt}/bin/${name}" "$out/bin/${name}"
  '';
}
