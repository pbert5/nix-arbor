{ lib, pkgs, changerDefault }:

let
  wrappedMtx = pkgs.writeShellApplication {
    name = "mtx";
    text = ''
      set -eu

      real_mtx="${lib.getExe' pkgs.mtx "mtx"}"
      default_changer="${lib.getExe changerDefault}"
      needs_device=1
      previous_was_flag=0

      for arg in "$@"; do
        if [ "$previous_was_flag" -eq 1 ]; then
          needs_device=0
          previous_was_flag=0
          continue
        fi

        case "$arg" in
          -f)
            needs_device=0
            previous_was_flag=1
            ;;
          -f*)
            needs_device=0
            ;;
        esac
      done

      if [ "$needs_device" -eq 1 ]; then
        if [ -n "''${CHANGER:-}" ]; then
          exec "$real_mtx" -f "$CHANGER" "$@"
        fi

        exec "$real_mtx" -f "$("$default_changer")" "$@"
      fi

      exec "$real_mtx" "$@"
    '';
  };
in
pkgs.symlinkJoin {
  name = "mtx-with-default-changer";
  paths = [
    pkgs.mtx
    wrappedMtx
  ];
  postBuild = ''
    rm "$out/bin/mtx"
    ln -s "${wrappedMtx}/bin/mtx" "$out/bin/mtx"
  '';
}
