import datetime as _dt
import json
import uuid
from pathlib import Path

VALID_STATES = {
    "planned",
    "staged",
    "private-delivered",
    "node-received",
    "node-activated",
    "leader-verified",
    "active",
    "deprecated",
    "removed",
    "burned",
}


def now_utc() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_event_id(prefix: str = "evt") -> str:
    return f"{prefix}-{_dt.datetime.now(_dt.UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:12]}"


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def iter_json_files(path: Path):
    if not path.exists():
        return
    for item in sorted(path.glob("*.json")):
        if item.is_file():
            yield item
