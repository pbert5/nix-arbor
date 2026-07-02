#!/usr/bin/env python3
"""File-compatible CLI for the Codex Switch VS Code extension."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STORE_DIR = ".codex-switch"
PROFILES_FILE = "profiles.json"
ACTIVE_PROFILE_FILE = "active-profile.json"
DEFAULT_HOME_ID = "default"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def home_dir() -> Path:
    return Path.home()


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", home_dir() / ".codex")).expanduser()


def codex_home_id() -> str:
    current = codex_home()
    default = home_dir() / ".codex"
    try:
        if current.resolve() == default.resolve():
            return DEFAULT_HOME_ID
    except OSError:
        if current == default:
            return DEFAULT_HOME_ID
    normalized = str(current.resolve())
    if os.name == "nt":
        normalized = normalized.lower()
    return f"env-{hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]}"


def store_root() -> Path:
    return home_dir() / STORE_DIR


def profiles_dir() -> Path:
    return store_root() / "profiles"


def active_profiles_dir() -> Path:
    return store_root() / "active-profiles"


def profiles_path() -> Path:
    return store_root() / PROFILES_FILE


def active_profile_path(home_id: str | None = None) -> Path:
    if home_id is None:
        return store_root() / ACTIVE_PROFILE_FILE
    return active_profiles_dir() / f"{home_id}.json"


def auth_path() -> Path:
    return codex_home() / "auth.json"


def ensure_store() -> None:
    store_root().mkdir(mode=0o700, parents=True, exist_ok=True)
    profiles_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    active_profiles_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
    for path in (store_root(), profiles_dir(), active_profiles_dir()):
        chmod_best_effort(path, 0o700)


def chmod_best_effort(path: Path, mode: int) -> None:
    if os.name == "nt":
        return
    try:
        path.chmod(mode)
    except OSError:
        pass


def read_json(path: Path, *, missing: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return missing
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any, *, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=f"{path.name}.tmp.{os.getpid()}.",
        dir=path.parent,
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
        chmod_best_effort(path, mode)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def read_profiles_file() -> dict[str, Any]:
    data = read_json(profiles_path(), missing={"version": 1, "profiles": []})
    if not isinstance(data, dict) or not isinstance(data.get("profiles"), list):
        raise SystemExit(f"Invalid profile index shape in {profiles_path()}")
    return data


def write_profiles_file(data: dict[str, Any]) -> None:
    ensure_store()
    if "version" not in data:
        data["version"] = 1
    write_json(profiles_path(), data)


def profile_secret_path(profile_id: str) -> Path:
    return profiles_dir() / f"{profile_id}.json"


def list_profiles() -> list[dict[str, Any]]:
    profiles = read_profiles_file()["profiles"]
    return [p for p in profiles if isinstance(p, dict)]


def find_profile(selector: str) -> dict[str, Any]:
    matches = [
        p
        for p in list_profiles()
        if p.get("id") == selector or str(p.get("name", "")).lower() == selector.lower()
    ]
    if not matches:
        raise SystemExit(f"No profile matches {selector!r}")
    if len(matches) > 1:
        names = ", ".join(str(p.get("name") or p.get("id")) for p in matches)
        raise SystemExit(f"Profile selector {selector!r} is ambiguous: {names}")
    return matches[0]


def current_active_id() -> str | None:
    explicit = read_json(active_profile_path(codex_home_id()), missing=None)
    if isinstance(explicit, dict) and isinstance(explicit.get("profileId"), str):
        return explicit["profileId"]
    legacy = read_json(active_profile_path(), missing=None)
    if isinstance(legacy, dict) and isinstance(legacy.get("profileId"), str):
        return legacy["profileId"]
    return infer_active_id_from_auth()


def set_active_id(profile_id: str | None) -> None:
    ensure_store()
    path = active_profile_path(codex_home_id())
    if profile_id is None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return
    data = {"profileId": profile_id, "updatedAt": now_iso()}
    write_json(path, data)
    if codex_home_id() == DEFAULT_HOME_ID:
        write_json(active_profile_path(), data)


def last_profile_path() -> Path:
    return store_root() / f"last-profile.{codex_home_id()}.json"


def get_last_id() -> str | None:
    data = read_json(last_profile_path(), missing=None)
    if isinstance(data, dict) and isinstance(data.get("profileId"), str):
        return data["profileId"]
    return None


def set_last_id(profile_id: str | None) -> None:
    if profile_id is None:
        try:
            last_profile_path().unlink()
        except FileNotFoundError:
            pass
        return
    ensure_store()
    write_json(last_profile_path(), {"profileId": profile_id, "updatedAt": now_iso()})


def decode_jwt_payload(token: str | None) -> dict[str, Any]:
    if not token or token.count(".") != 2:
        return {}
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8")
        data = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def nonempty(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def default_org(auth_payload: dict[str, Any]) -> tuple[str | None, str | None]:
    org_id = nonempty(auth_payload.get("selected_organization_id")) or nonempty(
        auth_payload.get("default_organization_id")
    )
    orgs = auth_payload.get("organizations")
    orgs = orgs if isinstance(orgs, list) else []
    if org_id:
        for org in orgs:
            if isinstance(org, dict) and nonempty(org.get("id")) == org_id:
                return org_id, nonempty(org.get("title"))
        return org_id, None
    for org in orgs:
        if isinstance(org, dict) and org.get("is_default"):
            return nonempty(org.get("id")), nonempty(org.get("title"))
    if orgs and isinstance(orgs[0], dict):
        return nonempty(orgs[0].get("id")), nonempty(orgs[0].get("title"))
    return None, None


def auth_data_from_auth_json(auth_json: Any) -> dict[str, Any] | None:
    if not isinstance(auth_json, dict) or not isinstance(auth_json.get("tokens"), dict):
        return None
    tokens = auth_json["tokens"]
    id_token = nonempty(tokens.get("id_token"))
    access_token = nonempty(tokens.get("access_token"))
    refresh_token = nonempty(tokens.get("refresh_token"))
    if not id_token or not access_token or not refresh_token:
        return None
    payload = decode_jwt_payload(id_token)
    auth_payload = payload.get("https://api.openai.com/auth")
    auth_payload = auth_payload if isinstance(auth_payload, dict) else {}
    org_id, org_title = default_org(auth_payload)
    return {
        "idToken": id_token,
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "accountId": nonempty(tokens.get("account_id")),
        "defaultOrganizationId": org_id,
        "defaultOrganizationTitle": org_title,
        "chatgptUserId": nonempty(auth_payload.get("chatgpt_user_id")),
        "userId": nonempty(auth_payload.get("user_id")),
        "subject": nonempty(payload.get("sub")),
        "email": nonempty(payload.get("email")) or "Unknown",
        "planType": nonempty(auth_payload.get("chatgpt_plan_type")) or "Unknown",
        "authJson": auth_json,
    }


def load_auth_file(path: Path) -> dict[str, Any] | None:
    return auth_data_from_auth_json(read_json(path, missing=None))


def read_profile_auth(profile_id: str) -> dict[str, Any]:
    data = read_json(profile_secret_path(profile_id), missing=None)
    if isinstance(data, dict) and isinstance(data.get("authJson"), dict):
        return data
    if isinstance(data, dict) and "accessToken" in data:
        return data
    raise SystemExit(f"Missing auth data for profile {profile_id}: {profile_secret_path(profile_id)}")


def write_auth_file(auth_data: dict[str, Any]) -> None:
    payload = auth_data.get("authJson")
    if not isinstance(payload, dict):
        payload = {
            "tokens": {
                "id_token": auth_data.get("idToken"),
                "access_token": auth_data.get("accessToken"),
                "refresh_token": auth_data.get("refreshToken"),
            }
        }
        if auth_data.get("accountId"):
            payload["tokens"]["account_id"] = auth_data["accountId"]
    if not isinstance(payload.get("tokens"), dict):
        raise SystemExit("Selected profile cannot produce a Codex auth.json payload")
    write_json(auth_path(), payload)


def profile_summary(profile: dict[str, Any]) -> str:
    name = profile.get("name") or profile.get("id")
    email = profile.get("email") or "Unknown"
    plan = profile.get("planType") or "Unknown"
    return f"{name} <{email}> [{plan}]"


def cmd_list(args: argparse.Namespace) -> int:
    active = current_active_id()
    for profile in list_profiles():
        marker = "*" if profile.get("id") == active else " "
        if args.ids:
            print(f"{marker} {profile.get('id')} {profile.get('name') or ''}".rstrip())
        else:
            print(f"{marker} {profile_summary(profile)}")
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    active = current_active_id()
    if not active:
        print("No active Codex Switch profile")
        return 1
    profile = find_profile(active)
    print(profile_summary(profile))
    print(f"id: {profile.get('id')}")
    print(f"codex_home: {codex_home()}")
    print(f"auth_json: {auth_path()}")
    return 0


def switch_to(selector: str) -> dict[str, Any]:
    profile = find_profile(selector)
    previous = current_active_id()
    profile_id = str(profile["id"])
    auth_data = read_profile_auth(profile_id)
    write_auth_file(auth_data)
    if previous and previous != profile_id:
        set_last_id(previous)
    set_active_id(profile_id)
    return profile


def cmd_switch(args: argparse.Namespace) -> int:
    profile = switch_to(args.profile)
    print(f"Active: {profile_summary(profile)}")
    return 0


def cmd_toggle(_args: argparse.Namespace) -> int:
    last = get_last_id()
    if not last:
        raise SystemExit("No previous profile recorded by this CLI")
    active = current_active_id()
    profile = switch_to(last)
    if active:
        set_last_id(active)
    print(f"Active: {profile_summary(profile)}")
    return 0


def infer_active_id_from_auth() -> str | None:
    live = load_auth_file(auth_path())
    if not live:
        return None
    live_account = live.get("accountId")
    live_subject = live.get("subject")
    for profile in list_profiles():
        if live_account and profile.get("accountId") == live_account:
            return str(profile.get("id"))
        if live_subject and profile.get("subject") == live_subject:
            return str(profile.get("id"))
    return None


def upsert_profile(name: str, auth_data: dict[str, Any]) -> dict[str, Any]:
    data = read_profiles_file()
    profiles = [p for p in data["profiles"] if isinstance(p, dict)]
    profile_id = str(uuid.uuid4())
    current = now_iso()
    profile = {
        "id": profile_id,
        "name": name,
        "email": auth_data.get("email") or "Unknown",
        "planType": auth_data.get("planType") or "Unknown",
        "createdAt": current,
        "updatedAt": current,
    }
    for key in (
        "accountId",
        "defaultOrganizationId",
        "defaultOrganizationTitle",
        "chatgptUserId",
        "userId",
        "subject",
    ):
        if auth_data.get(key):
            profile[key] = auth_data[key]

    for index, existing in enumerate(profiles):
        if existing.get("name") == name:
            profile["id"] = existing["id"]
            profile["createdAt"] = existing.get("createdAt", current)
            profiles[index] = profile
            write_profiles_file({"version": data.get("version", 1), "profiles": profiles})
            write_json(profile_secret_path(str(profile["id"])), auth_data)
            return profile

    profiles.append(profile)
    write_profiles_file({"version": data.get("version", 1), "profiles": profiles})
    write_json(profile_secret_path(profile_id), auth_data)
    return profile


def cmd_add_current(args: argparse.Namespace) -> int:
    source = Path(args.auth_file).expanduser() if args.auth_file else auth_path()
    auth_data = load_auth_file(source)
    if not auth_data:
        raise SystemExit(f"No usable Codex auth data in {source}")
    name = args.name or auth_data.get("email") or source.stem
    profile = upsert_profile(str(name), auth_data)
    if args.activate:
        set_active_id(str(profile["id"]))
    print(f"Saved: {profile_summary(profile)}")
    return 0


def cmd_prepare_login(_args: argparse.Namespace) -> int:
    set_active_id(None)
    try:
        auth_path().unlink()
        print(f"Removed {auth_path()}")
    except FileNotFoundError:
        print(f"No auth file at {auth_path()}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    destination = Path(args.path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profiles": read_profiles_file(),
        "secrets": {
            path.stem: read_json(path, missing={})
            for path in sorted(profiles_dir().glob("*.json"))
        },
    }
    write_json(destination, payload)
    print(f"Exported {destination}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    source = Path(args.path).expanduser()
    payload = read_json(source)
    if not isinstance(payload, dict) or not isinstance(payload.get("profiles"), dict):
        raise SystemExit(f"Invalid export file: {source}")
    write_profiles_file(payload["profiles"])
    secrets = payload.get("secrets")
    if isinstance(secrets, dict):
        ensure_store()
        for profile_id, secret in secrets.items():
            if isinstance(profile_id, str) and isinstance(secret, dict):
                write_json(profile_secret_path(profile_id), secret)
    print(f"Imported {source}")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    profile = find_profile(args.profile)
    profile_id = str(profile["id"])
    data = read_profiles_file()
    data["profiles"] = [p for p in data["profiles"] if not isinstance(p, dict) or p.get("id") != profile_id]
    write_profiles_file(data)
    try:
        profile_secret_path(profile_id).unlink()
    except FileNotFoundError:
        pass
    if current_active_id() == profile_id:
        set_active_id(None)
    if get_last_id() == profile_id:
        set_last_id(None)
    print(f"Deleted: {profile_summary(profile)}")
    return 0


def cmd_path(_args: argparse.Namespace) -> int:
    print(store_root())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-switch",
        description="Switch Codex auth profiles using the VS Code Codex Switch file store.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", aliases=["ls"], help="List saved profiles")
    list_cmd.add_argument("--ids", action="store_true", help="Show profile IDs")
    list_cmd.set_defaults(func=cmd_list)

    status = sub.add_parser("status", help="Show the active profile")
    status.set_defaults(func=cmd_status)

    switch = sub.add_parser("switch", help="Activate a profile by name or ID")
    switch.add_argument("profile")
    switch.set_defaults(func=cmd_switch)

    toggle = sub.add_parser("toggle", help="Switch back to the previous CLI profile")
    toggle.set_defaults(func=cmd_toggle)

    add_current = sub.add_parser("add-current", help="Save the current Codex auth.json as a profile")
    add_current.add_argument("name", nargs="?", help="Profile name; defaults to auth email")
    add_current.add_argument("--auth-file", help="Read auth data from this file instead of CODEX_HOME/auth.json")
    add_current.add_argument("--activate", action="store_true", help="Mark the saved profile active")
    add_current.set_defaults(func=cmd_add_current)

    prepare = sub.add_parser("prepare-login", help="Clear active profile state and remove auth.json")
    prepare.set_defaults(func=cmd_prepare_login)

    export = sub.add_parser("export", help="Export profiles and stored auth data")
    export.add_argument("path")
    export.set_defaults(func=cmd_export)

    import_cmd = sub.add_parser("import", help="Import profiles and stored auth data")
    import_cmd.add_argument("path")
    import_cmd.set_defaults(func=cmd_import)

    delete = sub.add_parser("delete", help="Delete a profile by name or ID")
    delete.add_argument("profile")
    delete.set_defaults(func=cmd_delete)

    path_cmd = sub.add_parser("path", help="Print the shared Codex Switch store path")
    path_cmd.set_defaults(func=cmd_path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
