import json
import shlex
import subprocess
from pathlib import Path

from .events import read_json
from .transport import host_bootstrap, nix_eval_json


BOOT_JSON_MARKER = "----- clusterctl boot.json -----"
FSTAB_MARKER = "----- clusterctl fstab -----"
REMOTE_BOOT_STATE = f"""
set -eu
system="$(readlink -f /run/current-system)"
printf '%s\\n' '{BOOT_JSON_MARKER}'
cat "$system/boot.json"
printf '%s\\n' '{FSTAB_MARKER}'
cat /etc/fstab
""".strip()


def _service_public(state: dict, host: str, service: str) -> dict:
    return ((state.get("nodes") or {}).get(host) or {}).get(service, {}).get("public", {})


def candidates(host: str, materialized: Path, flake: str = ".") -> list[tuple[str, str]]:
    active = read_json(materialized / "active.json", {}) or {}
    staged = read_json(materialized / "staged.json", {}) or {}
    deprecated = read_json(materialized / "deprecated.json", {}) or {}
    result: list[tuple[str, str]] = []
    for label, state in [
        ("active ygg", active),
        ("staged ygg", staged),
        ("deprecated ygg", deprecated),
    ]:
        public = _service_public(state, host, "yggdrasil")
        target = public.get("deployHost") or public.get("yggdrasilAddress")
        if target:
            result.append((label, target))
    bootstrap = host_bootstrap(flake).get(host, {})
    if bootstrap.get("targetHost"):
        result.append(("fallback host-bootstrap", bootstrap["targetHost"]))
    result.append(("plain host name", host))
    seen = set()
    unique = []
    for label, target in result:
        key = (label, target)
        if key not in seen:
            seen.add(key)
            unique.append((label, target))
    return unique


def _normalize_fstab(text: str) -> list[str]:
    return [
        " ".join(line.split())
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _normalize_boot_json(text: str) -> dict:
    data = json.loads(text)
    bootspec = data.get("org.nixos.bootspec.v1") or {}
    normalized = {
        key: value
        for key, value in data.items()
        if key != "org.nixos.bootspec.v1"
    }
    normalized["org.nixos.bootspec.v1"] = {
        key: bootspec.get(key)
        for key in [
            "initrd",
            "kernel",
            "kernelParams",
            "system",
        ]
    }
    return normalized


def boot_manifest(system: Path) -> dict:
    return {
        "boot": _normalize_boot_json((system / "boot.json").read_text()),
        "fstab": _normalize_fstab((system / "etc/fstab").read_text()),
    }


def _parse_remote_boot_state(output: str) -> dict:
    if BOOT_JSON_MARKER not in output or FSTAB_MARKER not in output:
        raise ValueError("remote output did not contain boot-state markers")
    boot_json, fstab = output.split(FSTAB_MARKER, 1)
    boot_json = boot_json.split(BOOT_JSON_MARKER, 1)[1]
    return {
        "boot": _normalize_boot_json(boot_json),
        "fstab": _normalize_fstab(fstab),
    }


def proposed_boot_manifest(host: str, flake: str) -> dict:
    completed = subprocess.run(
        [
            "nix",
            "build",
            "--no-link",
            "--print-out-paths",
            f"{flake}#nixosConfigurations.{host}.config.system.build.toplevel",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return boot_manifest(Path(completed.stdout.strip()))


def current_boot_manifest(host: str, flake: str) -> dict:
    node = nix_eval_json(f"deploy.nodes.{host}", flake)
    if not node:
        raise ValueError(f"missing deploy-rs target for {host}")
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        *(node.get("sshOpts") or []),
    ]
    command.extend(
        [
            f"{node.get('sshUser', 'root')}@{node['hostname']}",
            f"sh -c {shlex.quote(REMOTE_BOOT_STATE)}",
        ]
    )
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        timeout=20,
    )
    return _parse_remote_boot_state(completed.stdout)


def _error_summary(error: Exception) -> str:
    if isinstance(error, subprocess.CalledProcessError):
        return f"command exited with status {error.returncode}"
    if isinstance(error, subprocess.TimeoutExpired):
        return f"command timed out after {error.timeout} seconds"
    return str(error)


def boot_risk_reasons(host: str, flake: str) -> list[str]:
    try:
        proposed = proposed_boot_manifest(host, flake)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        return [f"cannot build proposed boot state: {_error_summary(error)}"]
    try:
        current = current_boot_manifest(host, flake)
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        return [f"cannot verify current boot state: {_error_summary(error)}"]

    reasons = []
    if current["fstab"] != proposed["fstab"]:
        reasons.append("generated fstab changes")
    if current["boot"] != proposed["boot"]:
        reasons.append("kernel, initrd, kernel parameters, or bootloader metadata changes")
    return reasons
