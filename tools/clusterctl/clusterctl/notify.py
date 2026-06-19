import subprocess
from pathlib import Path

from .deploy import candidates
from .transport import host_bootstrap


def notify_targets(targets: list[str], materialized: Path, flake: str = ".") -> None:
    bootstrap = host_bootstrap(flake)
    for target in targets:
        ssh_user = bootstrap.get(target, {}).get("sshUser") or "root"
        resolved = candidates(target, materialized, flake)
        if not resolved:
            continue
        chosen = resolved[0][1]
        subprocess.run(
            ["ssh", f"{ssh_user}@{chosen}", "systemctl", "start", "cluster-identity-fetch-now.service"],
            check=False,
        )
