from pathlib import Path

from .events import read_json
from .transport import host_bootstrap


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
