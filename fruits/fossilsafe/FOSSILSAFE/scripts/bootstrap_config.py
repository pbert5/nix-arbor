#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("FOSSILSAFE_AUTOSTART_SERVICES", "0")

from backend.config_store import load_config  # noqa: E402
from backend.auth import init_auth  # noqa: E402
from backend.database import Database  # noqa: E402
from backend.lto_backend_main import SourceManager  # noqa: E402


def load_bootstrap(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("Bootstrap payload must be a JSON object")
    return data


def normalize_source(source: Dict[str, Any], existing: Dict[str, Any] | None = None) -> Dict[str, Any]:
    existing = existing or {}
    config = source.get("config", {}) or {}
    source_id = source.get("id") or source.get("source_id")
    if not source_id:
        raise ValueError("Bootstrap source is missing id")

    source_type = source.get("source_type") or source.get("type") or existing.get("source_type") or "local"
    display_name = source.get("display_name") or source.get("name") or existing.get("display_name") or source_id
    source_path = source.get("source_path") or source.get("path") or config.get("path") or existing.get("source_path") or ""
    nfs_server = source.get("nfs_server") or config.get("nfs_server") or existing.get("nfs_server") or ""
    nfs_export = source.get("nfs_export") or config.get("nfs_export") or existing.get("nfs_export") or ""

    if source_type == "nfs" and not source_path:
        source_path = f"{nfs_server}:{nfs_export}".strip(":")

    payload = {
        "id": source_id,
        "source_type": source_type,
        "source_path": source_path,
        "display_name": display_name,
        "username": source.get("username") or config.get("username") or existing.get("username") or "",
        "domain": source.get("domain") or config.get("domain") or existing.get("domain") or "",
        "nfs_server": nfs_server,
        "nfs_export": nfs_export,
        "s3_bucket": source.get("s3_bucket") or config.get("bucket") or existing.get("s3_bucket") or "",
        "s3_region": source.get("s3_region") or config.get("region") or existing.get("s3_region") or "",
        "host": source.get("host") or config.get("host") or existing.get("host") or "",
        "port": source.get("port") or config.get("port") or existing.get("port") or 22,
    }

    password = source.get("password")
    if password is not None:
        payload["password"] = password
    elif existing.get("password_encrypted"):
        payload["password_encrypted"] = existing["password_encrypted"]

    return payload


def normalize_schedule(schedule: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    source_type = source.get("source_type") or "local"
    source_path = source.get("source_path") or ""
    if source_type == "nfs" and not source_path:
        nfs_server = source.get("nfs_server") or ""
        nfs_export = source.get("nfs_export") or ""
        source_path = f"{nfs_server}:{nfs_export}".strip(":")

    return {
        "name": schedule["name"],
        "source_id": source["id"],
        "cron": schedule["cron"],
        "tapes": list(schedule.get("tapes", [])),
        "verify": schedule.get("verify", True),
        "compression": schedule.get("compression", "zstd"),
        "duplicate": schedule.get("duplicate", False),
        "enabled": schedule.get("enabled", False),
        "drive": int(schedule.get("drive", 0) or 0),
        "backup_mode": schedule.get("backup_mode", "full"),
        "source_config": {
            "source_id": source["id"],
            "source_type": source_type,
            "source_path": source_path,
            "nfs_server": source.get("nfs_server", ""),
            "nfs_export": source.get("nfs_export", ""),
        },
    }


def apply_bootstrap(path: str) -> None:
    payload = load_bootstrap(path)
    runtime_config = load_config()
    db_path = runtime_config.get("db_path")
    if not db_path:
        raise RuntimeError("FossilSafe runtime config is missing db_path")

    db = Database(db_path)
    init_auth(db)
    source_manager = SourceManager(db)

    for key, value in (payload.get("settings") or {}).items():
        db.set_setting(key, value)

    if "oidc" in payload:
        db.set_setting("oidc_config", payload.get("oidc") or {"enabled": False})

    auth = payload.get("auth") or {}
    if auth.get("clear_existing_2fa"):
        db.execute("UPDATE users SET totp_secret = NULL")
        db.commit()

    for source in payload.get("sources", []) or []:
        existing = db.get_source(source.get("id") or source.get("source_id")) or {}
        normalized = normalize_source(source, existing=existing)
        source_manager.store_source(normalized)

    sources_by_id = {source["id"]: source for source in db.list_sources()}
    schedules_by_name = {schedule["name"]: schedule for schedule in db.get_schedules()}
    for schedule in payload.get("schedules", []) or []:
        source_id = schedule.get("source_id")
        if not source_id or source_id not in sources_by_id:
            raise ValueError(f"Bootstrap schedule '{schedule.get('name')}' references unknown source '{source_id}'")
        normalized = normalize_schedule(schedule, sources_by_id[source_id])
        existing = schedules_by_name.get(normalized["name"])
        if existing:
            db.update_schedule(
                existing["id"],
                name=normalized["name"],
                cron=normalized["cron"],
                tapes=normalized["tapes"],
                verify=normalized["verify"],
                compression=normalized["compression"],
                duplicate=normalized["duplicate"],
                enabled=normalized["enabled"],
                drive=normalized["drive"],
                backup_mode=normalized["backup_mode"],
                source_id=normalized["source_id"],
                source_config=normalized["source_config"],
            )
        else:
            db.create_schedule(
                name=normalized["name"],
                source_id=normalized["source_id"],
                cron=normalized["cron"],
                tapes=normalized["tapes"],
                verify=normalized["verify"],
                compression=normalized["compression"],
                duplicate=normalized["duplicate"],
                enabled=normalized["enabled"],
                source_config=normalized["source_config"],
                drive=normalized["drive"],
                backup_mode=normalized["backup_mode"],
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply declarative FossilSafe bootstrap data")
    parser.add_argument("bootstrap_path", help="Path to bootstrap JSON file")
    args = parser.parse_args()
    apply_bootstrap(args.bootstrap_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
