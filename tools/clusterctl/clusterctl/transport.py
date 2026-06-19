import json
import os
import subprocess
from pathlib import Path


def run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True)


def capture(cmd: list[str]) -> str | None:
    try:
        completed = subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def ensure_git_identity(registry: Path) -> None:
    if not (registry / ".git").exists():
        return
    if not capture(["git", "-C", str(registry), "config", "--local", "user.name"]):
        subprocess.run(
            [
                "git",
                "-C",
                str(registry),
                "config",
                "--local",
                "user.name",
                "Cluster Identity Registry",
            ],
            check=False,
        )
    if not capture(["git", "-C", str(registry), "config", "--local", "user.email"]):
        subprocess.run(
            [
                "git",
                "-C",
                str(registry),
                "config",
                "--local",
                "user.email",
                "cluster-identity@localhost",
            ],
            check=False,
        )


def git_commit_if_possible(registry: Path, message: str) -> None:
    if not (registry / ".git").exists():
        return
    ensure_git_identity(registry)
    subprocess.run(["git", "-C", str(registry), "add", "."], check=False)
    subprocess.run(["git", "-C", str(registry), "commit", "-m", message], check=False)


def git_remotes(registry: Path) -> list[str]:
    out = capture(["git", "-C", str(registry), "remote"])
    if not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def git_remote_url(registry: Path, name: str) -> str | None:
    return capture(["git", "-C", str(registry), "remote", "get-url", name])


def sync_git_remotes(registry: Path, remotes: dict, prune: bool = False) -> list[str]:
    changed: list[str] = []
    if not (registry / ".git").exists():
        return changed
    existing = set(git_remotes(registry))
    desired = set()
    for name in sorted(remotes.keys()):
        remote = remotes.get(name) or {}
        url = remote.get("url") if isinstance(remote, dict) else None
        if not url:
            continue
        desired.add(name)
        current = git_remote_url(registry, name)
        if current is None:
            subprocess.run(["git", "-C", str(registry), "remote", "add", name, url], check=False)
            changed.append(f"added {name}")
        elif current != url:
            subprocess.run(["git", "-C", str(registry), "remote", "set-url", name, url], check=False)
            changed.append(f"updated {name}")
    if prune:
        for name in sorted(existing - desired):
            subprocess.run(["git", "-C", str(registry), "remote", "remove", name], check=False)
            changed.append(f"removed {name}")
    return changed


def git_environment(policy: dict | None = None) -> dict | None:
    policy = policy or {}
    registry = policy.get("registry") or {}
    transport = registry.get("transport") or {}
    ssh_command = transport.get("gitSshCommand")
    if not ssh_command:
        return None
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = ssh_command
    return env


def policy_remotes(policy: dict, mode: str = "all") -> list[str]:
    remotes = ((policy.get("registry") or {}).get("remotes") or {})
    selected: list[str] = []
    for name, remote in sorted(remotes.items()):
        if not isinstance(remote, dict) or not remote.get("url"):
            continue
        if mode == "fetch" and remote.get("fetch") is False:
            continue
        if mode == "push" and remote.get("push") is False:
            continue
        selected.append(name)
    return selected


def git_fetch_all(registry: Path, policy: dict | None = None) -> None:
    if (registry / ".git").exists():
        subprocess.run(
            ["git", "-C", str(registry), "fetch", "--all", "--prune"],
            check=False,
            env=git_environment(policy),
        )


def git_push_remotes(registry: Path, remotes: list[str] | None = None, policy: dict | None = None) -> list[str]:
    selected = remotes or git_remotes(registry)
    for remote in selected:
        subprocess.run(
            ["git", "-C", str(registry), "push", remote, "HEAD:main"],
            check=False,
            env=git_environment(policy),
        )
    return selected


def nix_eval_json(attr: str, flake: str = "."):
    out = capture(["nix", "eval", "--json", f"{flake}#{attr}"])
    if out is None:
        return None
    return json.loads(out)


def inventory(flake: str = ".") -> dict:
    return nix_eval_json("inventory", flake) or {}


def host_bootstrap(flake: str = ".") -> dict:
    return inventory(flake).get("hostBootstrap", {})
