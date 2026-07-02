import json
from pathlib import Path


def read_lock(flake_root: Path) -> dict:
    return json.loads((flake_root / "flake.lock").read_text())


def top_level_locked(lock: dict) -> dict[str, dict]:
    root_inputs = lock["nodes"][lock["root"]].get("inputs", {})
    return {
        name: lock["nodes"][node]
        for name, node in root_inputs.items()
        if isinstance(node, str)
    }


def _locked_id(node: dict) -> tuple:
    locked = node.get("locked", {})
    return (locked.get("narHash"), locked.get("rev"))


def diff_top_level(before: dict, after: dict) -> list[str]:
    changes = []
    for name in sorted(after):
        old = before.get(name)
        new = after[name]
        if old is not None and _locked_id(old) == _locked_id(new):
            continue
        old_rev = ((old or {}).get("locked", {}).get("rev") or "")[:7]
        new_rev = (new.get("locked", {}).get("rev") or "")[:7]
        if old is None:
            changes.append(f"{name}: added ({new_rev or 'no rev'})")
        elif old_rev and new_rev:
            changes.append(f"{name}: {old_rev} -> {new_rev}")
        else:
            changes.append(f"{name}: updated")
    return changes
