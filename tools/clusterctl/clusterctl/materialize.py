import shutil
from pathlib import Path


def materialize_state(registry: Path, out: Path) -> None:
    state = registry / "state"
    out.mkdir(parents=True, exist_ok=True)
    for name in [
        "active.json",
        "staged.json",
        "deprecated.json",
        "burned.json",
    ]:
        src = state / name
        if src.exists():
            shutil.copy2(src, out / name)
    known_hosts = state / "known_hosts"
    if known_hosts.exists():
        shutil.copy2(known_hosts, out / "ssh_known_hosts")
    for subdir, filename in [
        ("yggdrasil", "peers.json"),
        ("radicle", "nodes.json"),
        ("git-annex", "remotes.json"),
    ]:
        src = state / f"{subdir}-{filename}"
        target_dir = out / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, target_dir / filename)
