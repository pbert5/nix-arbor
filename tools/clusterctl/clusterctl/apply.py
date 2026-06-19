from pathlib import Path
import subprocess


def apply_materialized(_registry: Path, materialized: Path, policy: dict | None = None) -> None:
    materialized.mkdir(parents=True, exist_ok=True)
    policy = policy or {}
    services = (((policy.get("registry") or {}).get("apply") or {}).get("reloadServices") or [])
    for service in services:
        subprocess.run(["systemctl", "try-reload-or-restart", service], check=False)
