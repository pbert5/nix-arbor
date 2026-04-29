#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            merged[key] = deep_merge(merged[key], value) if key in merged else value
        return merged
    return overlay


def guess_flake_root() -> Path | None:
    for candidate in (Path.cwd(), *Path.cwd().parents):
        if (candidate / "flake.nix").exists() and (candidate / "inventory" / "hosts.nix").exists():
            return candidate
    return None


def run_json(command: list[str], *, error_hint: str) -> Any:
    try:
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise SystemExit(f"{error_hint}: {message}") from exc

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{error_hint}: failed to decode JSON output") from exc


def nix_inventory(flake_path: Path, host_name: str) -> dict[str, Any]:
    expr = f'''
let
  flakePath = builtins.toPath {json.dumps(str(flake_path))};
  hosts = import (flakePath + "/inventory/hosts.nix") {{ inputs = null; }};
  ports = import (flakePath + "/inventory/ports.nix");
in {{
  host = builtins.getAttr {json.dumps(host_name)} hosts;
  ports = ports;
}}
'''
    return run_json(
        ["nix", "eval", "--json", "--impure", "--expr", expr],
        error_hint=f"Failed to read inventory for host '{host_name}'",
    )


def normalise_state_dir(state_dir: Path) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    for child in [
        "catalog-backups",
        "diagnostics",
        "hooks.d",
        "staging",
        "tmp",
    ]:
        (state_dir / child).mkdir(parents=True, exist_ok=True)
    return state_dir


def build_runtime(host_data: dict[str, Any], state_dir: Path) -> tuple[dict[str, Any], dict[str, Any], bool]:
    host = host_data["host"]
    ports = host_data["ports"]

    tape_facts = host.get("facts", {}).get("storage", {}).get("tape", {}).get("devices", {})
    tape_org = host.get("org", {}).get("storage", {}).get("tape", {})
    fossilsafe_org = tape_org.get("fossilsafe", {})
    endpoint = ports.get("tapeLibraryFossilsafe", {})

    bind = endpoint.get("bind", "127.0.0.1")
    port = endpoint.get("port", 5001)
    hosts = endpoint.get("hosts", ["127.0.0.1", "localhost"])

    drive_devices = tape_facts.get("drives") or ([tape_facts["drive"]] if tape_facts.get("drive") else [])
    drive_device = tape_facts.get("drive") or (drive_devices[0] if drive_devices else None)
    changer_device = tape_facts.get("changer")

    device_settings: dict[str, Any] = {}
    tape_settings: dict[str, Any] = {}
    if changer_device:
        tape_settings["changer_device"] = changer_device
    if drive_device:
        tape_settings["drive_device"] = drive_device
    if drive_devices:
        tape_settings["drive_devices"] = drive_devices
    if tape_settings:
        device_settings["tape"] = tape_settings

    default_settings: dict[str, Any] = {
        "allowed_origins": [f"http://{host_name}:{port}" for host_name in hosts],
        "backend_bind": bind,
        "backend_port": port,
        "catalog_backup_dir": str(state_dir / "catalog-backups"),
        "credential_key_path": str(state_dir / "credential_key.bin"),
        "db_path": str(state_dir / "lto_backup.db"),
        "diagnostics_dir": str(state_dir / "diagnostics"),
        "headless": False,
        "staging_dir": str(state_dir / "staging"),
    }

    settings = deep_merge(default_settings, fossilsafe_org.get("settings", {}))
    settings = deep_merge(settings, device_settings)
    bootstrap = fossilsafe_org.get("bootstrap", {})
    require_api_key = bool(fossilsafe_org.get("requireApiKey", False))
    return settings, bootstrap, require_api_key


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local FossilSafe fork as an experiment without enabling the NixOS service."
    )
    parser.add_argument("--flake", help="Path to the main flake repo. Auto-detected from the current directory when omitted.")
    parser.add_argument("--host", default="desktoptoodle", help="Inventory host to read FossilSafe settings from.")
    parser.add_argument(
        "--state-dir",
        help="Experiment state directory. Defaults to ~/.local/state/fossilsafe-experiments/<host>.",
    )
    parser.add_argument("--skip-bootstrap", action="store_true", help="Skip applying inventory bootstrap data before launch.")
    parser.add_argument("--print-config", action="store_true", help="Render the derived config and exit.")
    parser.add_argument("--fossilsafe-bin", required=True, help=argparse.SUPPRESS)
    parser.add_argument("--bootstrap-bin", required=True, help=argparse.SUPPRESS)
    parser.add_argument("fossilsafe_args", nargs=argparse.REMAINDER, help="Arguments passed through to the FossilSafe launcher.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.fossilsafe_args[:1] == ["--"]:
        args.fossilsafe_args = args.fossilsafe_args[1:]

    flake_path = Path(args.flake).expanduser().resolve() if args.flake else guess_flake_root()
    if flake_path is None:
        raise SystemExit("Unable to detect the main flake repo. Pass --flake /path/to/flake.")

    default_state_dir = Path.home() / ".local" / "state" / "fossilsafe-experiments" / args.host
    state_dir = normalise_state_dir(Path(args.state_dir).expanduser().resolve() if args.state_dir else default_state_dir)

    host_data = nix_inventory(flake_path, args.host)
    settings, bootstrap, require_api_key = build_runtime(host_data, state_dir)

    config_path = state_dir / "config.generated.json"
    bootstrap_path = state_dir / "bootstrap.generated.json"
    write_json(config_path, settings)
    if bootstrap:
        write_json(bootstrap_path, bootstrap)

    summary = {
        "flake": str(flake_path),
        "host": args.host,
        "state_dir": str(state_dir),
        "config_path": str(config_path),
        "bootstrap_path": str(bootstrap_path) if bootstrap else None,
        "require_api_key": require_api_key,
    }

    if args.print_config:
        print(json.dumps({"summary": summary, "settings": settings, "bootstrap": bootstrap}, indent=2, sort_keys=True))
        return 0

    print(f"[fossilsafe-lab] host={args.host} flake={flake_path}")
    print(f"[fossilsafe-lab] state dir: {state_dir}")
    print(f"[fossilsafe-lab] config: {config_path}")
    if bootstrap and not args.skip_bootstrap:
        print(f"[fossilsafe-lab] bootstrap: {bootstrap_path}")
    elif bootstrap:
        print("[fossilsafe-lab] bootstrap present but skipped")

    env = os.environ.copy()
    env.update(
        {
            "FOSSILSAFE_BACKEND_BIND": str(settings.get("backend_bind", "127.0.0.1")),
            "FOSSILSAFE_BACKEND_PORT": str(settings.get("backend_port", 5001)),
            "FOSSILSAFE_CATALOG_BACKUP_DIR": str(state_dir / "catalog-backups"),
            "FOSSILSAFE_CONFIG_PATH": str(config_path),
            "FOSSILSAFE_DATA_DIR": str(state_dir),
            "FOSSILSAFE_DIAGNOSTICS_DIR": str(state_dir / "diagnostics"),
            "FOSSILSAFE_HOOKS_DIR": str(state_dir / "hooks.d"),
            "FOSSILSAFE_REQUIRE_API_KEY": "true" if require_api_key else "false",
            "FOSSILSAFE_STATE_PATH": str(state_dir / "state.json"),
            "FOSSILSAFE_VAR_DIR": str(state_dir / "tmp"),
            "HOME": str(state_dir),
        }
    )

    if bootstrap and not args.skip_bootstrap:
        subprocess.run([args.bootstrap_bin, str(bootstrap_path)], check=True, env=env)

    os.execvpe(args.fossilsafe_bin, [args.fossilsafe_bin, *args.fossilsafe_args], env)


if __name__ == "__main__":
    raise SystemExit(main())
