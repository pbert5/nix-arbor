{
  lib,
  pkgs,
  fetchzip,
  stdenvNoCC,
  symlinkJoin,
  tapeDefault,
  ltfsOpen,
  mtWithDefaults,
  yatmPort ? 8081,
  yatmDebugPort ? 8082,
}:

let
  version = "0.1.21";

  src = fetchzip {
    url = "https://github.com/samuelncui/yatm/releases/download/v${version}/yatm-linux-amd64-v${version}.tar.gz";
    hash = "sha256-F5k4dTIjdCsqUCiyUJDWNlAFSm5lCYfDWA3V7bAUDXM=";
    stripRoot = false;
  };

  yatmUnwrapped = stdenvNoCC.mkDerivation {
    pname = "yatm-unwrapped";
    inherit version src;

    dontConfigure = true;
    dontBuild = true;

    installPhase = ''
      runHook preInstall

      mkdir -p "$out/share/yatm"
      cp -r ${src}/* "$out/share/yatm/"

      chmod +x \
        "$out/share/yatm/yatm-httpd" \
        "$out/share/yatm/yatm-export-library" \
        "$out/share/yatm/yatm-lto-info" \
        "$out/share/yatm/scripts/"*

      substituteInPlace "$out/share/yatm/scripts/readinfo" \
        --replace-fail "./yatm-lto-info" "$out/share/yatm/yatm-lto-info"

      substituteInPlace \
        "$out/share/yatm/scripts/mount" \
        "$out/share/yatm/scripts/mount.openltfs" \
        --replace-fail "/opt/yatm/captured_indices" '${"$"}{YATM_CAPTURED_INDICES_DIR:-./captured_indices}'

      runHook postInstall
    '';
  };

  runtimeInputs =
    [
      pkgs.coreutils
      pkgs.gawk
      pkgs.gnugrep
      pkgs.gnused
      pkgs.sg3_utils
      pkgs."util-linux"
      ltfsOpen
      mtWithDefaults
    ]
    ++ lib.optional (pkgs ? stenc) pkgs.stenc;

  runtimeSetup = ''
    set -euo pipefail

    if [ -n "''${YATM_CONFIG:-}" ]; then
      config_path="$YATM_CONFIG"
    elif [ -r /etc/yatm/config.yaml ]; then
      config_path=/etc/yatm/config.yaml
    else
      config_path="''${XDG_CONFIG_HOME:-$HOME/.config}/yatm/config.yaml"
    fi

    config_dir="$(dirname "$config_path")"
    state_dir="''${YATM_STATE_DIR:-''${XDG_STATE_HOME:-$HOME/.local/state}/yatm}"
    runtime_dir="$state_dir/runtime"
    captured_indices_dir="''${YATM_CAPTURED_INDICES_DIR:-$state_dir/captured_indices}"
    source_dir="''${YATM_SOURCE_DIR:-$HOME}"
    target_dir="''${YATM_TARGET_DIR:-$HOME}"

    mkdir -p \
      "$state_dir" \
      "$runtime_dir" \
      "$captured_indices_dir"

    ln -sfn "${yatmUnwrapped}/share/yatm/frontend" "$runtime_dir/frontend"

    if [ ! -e "$config_path" ]; then
      mkdir -p "$config_dir"

      if default_tape="$(${lib.getExe tapeDefault} 2>/dev/null)"; then
        :
      else
        default_tape="/dev/nst0"
      fi

      cat > "$config_path" <<EOF
domain: http://127.0.0.1:${toString yatmPort}
listen: 127.0.0.1:${toString yatmPort}
debug_listen: 127.0.0.1:${toString yatmDebugPort}

database:
  dialect: sqlite
  dsn: ${"$"}{state_dir}/tapes.db

tape_devices:
  - ${"$"}{default_tape}

paths:
  work: ${"$"}{state_dir}/work
  source: ${"$"}{source_dir}
  target: ${"$"}{target_dir}

scripts:
  encrypt: ${yatmUnwrapped}/share/yatm/scripts/encrypt
  mkfs: ${yatmUnwrapped}/share/yatm/scripts/mkfs
  mount: ${yatmUnwrapped}/share/yatm/scripts/mount
  umount: ${yatmUnwrapped}/share/yatm/scripts/umount
  read_info: ${yatmUnwrapped}/share/yatm/scripts/readinfo
EOF
    fi

    export YATM_CAPTURED_INDICES_DIR="$captured_indices_dir"

    mkdir -p "$state_dir/work"
    cd "$runtime_dir"
  '';

  yatmLauncher = pkgs.writeShellApplication {
    name = "yatm";
    inherit runtimeInputs;
    text = ''
      ${runtimeSetup}
      exec ${yatmUnwrapped}/share/yatm/yatm-httpd -config "$config_path" "$@"
    '';
  };

  yatmHttpdLauncher = pkgs.writeShellApplication {
    name = "yatm-httpd";
    inherit runtimeInputs;
    text = ''
      ${runtimeSetup}
      exec ${yatmUnwrapped}/share/yatm/yatm-httpd -config "$config_path" "$@"
    '';
  };

  yatmExportLibraryLauncher = pkgs.writeShellApplication {
    name = "yatm-export-library";
    inherit runtimeInputs;
    text = ''
      ${runtimeSetup}
      exec ${yatmUnwrapped}/share/yatm/yatm-export-library -config "$config_path" "$@"
    '';
  };

  yatmLtoInfoLauncher = pkgs.writeShellApplication {
    name = "yatm-lto-info";
    runtimeInputs = [
      pkgs.coreutils
      pkgs.sg3_utils
    ];
    text = ''
      set -euo pipefail
      exec ${yatmUnwrapped}/share/yatm/yatm-lto-info "$@"
    '';
  };
in
symlinkJoin {
  name = "yatm";
  paths = [
    yatmUnwrapped
    yatmLauncher
    yatmHttpdLauncher
    yatmExportLibraryLauncher
    yatmLtoInfoLauncher
  ];

  meta = {
    description = "Web UI and helpers for LTFS-backed LTO tape management";
    homepage = "https://github.com/samuelncui/yatm";
    license = lib.licenses.bsd2;
    mainProgram = "yatm";
    platforms = [ "x86_64-linux" ];
  };
}
