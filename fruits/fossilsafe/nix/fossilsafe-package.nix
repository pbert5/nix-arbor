{
  lib,
  pkgs,
  buildNpmPackage,
  python3,
  sourceRoot,
  stdenvNoCC,
  symlinkJoin,
  ltfsOpen,
}:

let
  src = lib.cleanSourceWith {
    src = sourceRoot;
    filter =
      path: type:
      let
        baseName = builtins.baseNameOf path;
      in
      !(builtins.elem baseName [
        ".git"
        ".pytest_cache"
        "__pycache__"
        "dist"
        "node_modules"
      ]);
  };

  version = "fork-local-2026-04-20";
  frontendSourceRoot = "source/frontend";
  frontendNpmDepsHash = "sha256-RSimP0P7PYBJDsfPPYJpRNx/QhiYBf+bfu1PaJl1LUg=";
  frontendPostPatch = "";

  frontend = buildNpmPackage {
    pname = "fossilsafe-frontend";
    inherit version src;

    sourceRoot = frontendSourceRoot;
    npmDepsHash = frontendNpmDepsHash;
    postPatch = frontendPostPatch;

    installPhase = ''
      runHook preInstall
      mkdir -p "$out/dist"
      cp -r dist/* "$out/dist/"
      runHook postInstall
    '';
  };

  pythonEnv = python3.withPackages (
    ps: with ps; [
      apscheduler
      argon2-cffi
      bidict
      blinker
      boto3
      certifi
      cffi
      charset-normalizer
      click
      cryptography
      dnspython
      eventlet
      flask
      flask-cors
      flask-socketio
      flask-wtf
      gevent
      greenlet
      gunicorn
      h11
      hypothesis
      idna
      iniconfig
      itsdangerous
      jinja2
      markupsafe
      packaging
      pluggy
      ply
      pyasn1
      pycparser
      pycryptodomex
      pygments
      pyotp
      pysmi
      pysnmp
      pytest
      pytest-asyncio
      python-engineio
      python-socketio
      pytz
      requests
      rich
      simple-websocket
      six
      tzlocal
      urllib3
      websocket-client
      werkzeug
      wsproto
      wtforms
      zope-event
      zope-interface
    ]
  );

  fossilsafeUnwrapped = stdenvNoCC.mkDerivation {
    pname = "fossilsafe-unwrapped";
    inherit version src;

    dontConfigure = true;
    dontBuild = true;

    installPhase = ''
      runHook preInstall

      mkdir -p "$out/share/fossilsafe/frontend"

      cp -r \
        ${src}/backend \
        ${src}/docs \
        ${src}/scripts \
        "$out/share/fossilsafe/"

      cp \
        ${src}/ARCHITECTURE.md \
        ${src}/LICENSE \
        ${src}/README.md \
        ${src}/THIRD_PARTY_NOTICES.md \
        ${src}/gunicorn.conf.py \
        ${src}/requirements.txt \
        "$out/share/fossilsafe/"

      cp -r ${frontend}/dist "$out/share/fossilsafe/frontend/"

      substituteInPlace "$out/share/fossilsafe/backend/services/hook_service.py" \
        --replace-fail 'def __init__(self, hooks_dir: str = "/etc/fossilsafe/hooks.d"):' \
        'def __init__(self, hooks_dir: str = os.environ.get("FOSSILSAFE_HOOKS_DIR", "/etc/fossilsafe/hooks.d")):'

      chmod +x \
        "$out/share/fossilsafe/backend/lto_backend_main.py" \
        "$out/share/fossilsafe/scripts/fossilsafe_cli.py" \
        "$out/share/fossilsafe/scripts/smoke_test.sh"

      runHook postInstall
    '';
  };

  runtimeInputs = [
    pkgs.attr
    pkgs.coreutils
    pkgs.findutils
    pkgs.fuse3
    pkgs.gawk
    pkgs.gnutar
    pkgs.gnugrep
    pkgs.gnupg
    pkgs.gnused
    pkgs.gzip
    pkgs.lsscsi
    ltfsOpen
    pkgs.lz4
    pkgs.mtx
    pkgs.openssh
    pkgs.rclone
    pkgs.rsync
    pkgs.samba
    pkgs.sg3_utils
    pkgs."mt-st"
    pkgs."nfs-utils"
    pkgs."util-linux"
    pkgs.which
    pkgs.zstd
  ] ++ lib.optionals (builtins.hasAttr "cifs-utils" pkgs) [ pkgs."cifs-utils" ];

  runtimeSetup = ''
    set -euo pipefail

    find_default_drive() {
      local candidate
      for candidate in /dev/tape/by-id/REPLACE_ME
        if [ -e "$candidate" ]; then
          printf '%s\n' "$candidate"
          return 0
        fi
      done
      return 1
    }

    find_default_changer() {
      local candidate
      for candidate in /dev/tape/by-id/REPLACE_ME
        if [ -e "$candidate" ]; then
          printf '%s\n' "$candidate"
          return 0
        fi
      done
      return 1
    }

    config_dir="''${XDG_CONFIG_HOME:-$HOME/.config}/fossilsafe"
    data_dir="''${FOSSILSAFE_DATA_DIR:-''${XDG_STATE_HOME:-$HOME/.local/state}/fossilsafe}"

    mkdir -p \
      "$config_dir" \
      "$data_dir" \
      "$data_dir/catalog-backups" \
      "$data_dir/diagnostics" \
      "$data_dir/hooks.d" \
      "$data_dir/staging" \
      "$data_dir/tmp"

    export FOSSILSAFE_CONFIG_PATH="''${FOSSILSAFE_CONFIG_PATH:-$config_dir/config.json}"
    export FOSSILSAFE_DATA_DIR="$data_dir"
    export FOSSILSAFE_STATE_PATH="''${FOSSILSAFE_STATE_PATH:-$data_dir/state.json}"
    export FOSSILSAFE_CATALOG_BACKUP_DIR="''${FOSSILSAFE_CATALOG_BACKUP_DIR:-$data_dir/catalog-backups}"
    export FOSSILSAFE_DIAGNOSTICS_DIR="''${FOSSILSAFE_DIAGNOSTICS_DIR:-$data_dir/diagnostics}"
    export FOSSILSAFE_HOOKS_DIR="''${FOSSILSAFE_HOOKS_DIR:-$data_dir/hooks.d}"
    export FOSSILSAFE_VAR_DIR="''${FOSSILSAFE_VAR_DIR:-$data_dir/tmp}"
    export FOSSILSAFE_BACKEND_BIND="''${FOSSILSAFE_BACKEND_BIND:-127.0.0.1}"
    export FOSSILSAFE_BACKEND_PORT="''${FOSSILSAFE_BACKEND_PORT:-5001}"

    if [ ! -e "$FOSSILSAFE_CONFIG_PATH" ]; then
      if default_drive="$(find_default_drive 2>/dev/null)"; then
        export FOSSILSAFE_DEFAULT_DRIVE="$default_drive"
      else
        export FOSSILSAFE_DEFAULT_DRIVE=""
      fi

      if default_changer="$(find_default_changer 2>/dev/null)"; then
        export FOSSILSAFE_DEFAULT_CHANGER="$default_changer"
      else
        export FOSSILSAFE_DEFAULT_CHANGER=""
      fi

      ${pythonEnv}/bin/python - <<'PY'
import json
import os

config = {
    "backend_bind": os.environ.get("FOSSILSAFE_BACKEND_BIND", "127.0.0.1"),
    "backend_port": int(os.environ.get("FOSSILSAFE_BACKEND_PORT", "5001")),
    "catalog_backup_dir": os.environ["FOSSILSAFE_CATALOG_BACKUP_DIR"],
    "credential_key_path": os.path.join(os.environ["FOSSILSAFE_DATA_DIR"], "credential_key.bin"),
    "db_path": os.path.join(os.environ["FOSSILSAFE_DATA_DIR"], "lto_backup.db"),
    "diagnostics_dir": os.environ["FOSSILSAFE_DIAGNOSTICS_DIR"],
    "headless": False,
    "staging_dir": os.path.join(os.environ["FOSSILSAFE_DATA_DIR"], "staging"),
}

tape = {}

default_drive = os.environ.get("FOSSILSAFE_DEFAULT_DRIVE")
if default_drive:
    tape["drive_device"] = default_drive
    tape["drive_devices"] = [default_drive]

default_changer = os.environ.get("FOSSILSAFE_DEFAULT_CHANGER")
if default_changer:
    tape["changer_device"] = default_changer

if tape:
    config["tape"] = tape

config_path = os.environ["FOSSILSAFE_CONFIG_PATH"]
os.makedirs(os.path.dirname(config_path), exist_ok=True)

with open(config_path, "w", encoding="utf-8") as handle:
    json.dump(config, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
    fi
  '';

  fossilsafeLauncher = pkgs.writeShellApplication {
    name = "fossilsafe";
    inherit runtimeInputs;
    text = ''
      ${runtimeSetup}
      cd ${fossilsafeUnwrapped}/share/fossilsafe
      exec ${pythonEnv}/bin/python -m backend.lto_backend_main \
        --host "$FOSSILSAFE_BACKEND_BIND" \
        --port "$FOSSILSAFE_BACKEND_PORT" \
        "$@"
    '';
  };

  fossilsafeCliLauncher = pkgs.writeShellApplication {
    name = "fossilsafe-cli";
    inherit runtimeInputs;
    text = ''
      set -euo pipefail
      export FOSSILSAFE_API_URL="''${FOSSILSAFE_API_URL:-http://127.0.0.1:''${FOSSILSAFE_BACKEND_PORT:-5001}}"
      exec ${pythonEnv}/bin/python ${fossilsafeUnwrapped}/share/fossilsafe/scripts/fossilsafe_cli.py "$@"
    '';
  };

  fossilsafeSmokeTestLauncher = pkgs.writeShellApplication {
    name = "fossilsafe-smoke-test";
    inherit runtimeInputs;
    text = ''
      ${runtimeSetup}
      exec ${fossilsafeUnwrapped}/share/fossilsafe/scripts/smoke_test.sh "$@"
    '';
  };

  fossilsafeBootstrapLauncher = pkgs.writeShellApplication {
    name = "fossilsafe-bootstrap";
    inherit runtimeInputs;
    text = ''
      ${runtimeSetup}
      cd ${fossilsafeUnwrapped}/share/fossilsafe
      exec ${pythonEnv}/bin/python ${fossilsafeUnwrapped}/share/fossilsafe/scripts/bootstrap_config.py "$@"
    '';
  };
in
symlinkJoin {
  name = "fossilsafe";
  paths = [
    fossilsafeUnwrapped
    fossilsafeLauncher
    fossilsafeBootstrapLauncher
    fossilsafeCliLauncher
    fossilsafeSmokeTestLauncher
  ];

  passthru = {
    inherit
      frontend
      frontendNpmDepsHash
      frontendPostPatch
      frontendSourceRoot
      pythonEnv
      src
      version
      ;
  };

  meta = {
    description = "Fork-local LTO LTFS archival workflow UI for drives and tape libraries";
    homepage = "https://github.com/pbert5/FOSSILSAFE";
    license = lib.licenses.agpl3Plus;
    mainProgram = "fossilsafe";
    platforms = lib.platforms.linux;
  };
}
