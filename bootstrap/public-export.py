#!/usr/bin/env python3
"""Export a sanitized public mirror of the repo from an allowlisted subset."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or refresh a sanitized public mirror of this repo."
    )
    parser.add_argument(
        "--source",
        default=os.getcwd(),
        help="Path to the private source repo. Defaults to the current directory.",
    )
    parser.add_argument(
        "--destination",
        required=True,
        help="Path to the public mirror checkout to create or refresh.",
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("PUBLIC_EXPORT_CONFIG"),
        help="Path to the export config JSON. Defaults to PUBLIC_EXPORT_CONFIG.",
    )
    parser.add_argument(
        "--overlay",
        default=os.environ.get("PUBLIC_EXPORT_OVERLAY"),
        help="Path to overlay files that replace copied files. Defaults to PUBLIC_EXPORT_OVERLAY.",
    )
    parser.add_argument(
        "--skip-lock-refresh",
        action="store_true",
        help="Do not run `nix flake lock` in the destination after export.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied and sanitized without writing files.",
    )
    parser.add_argument(
        "--skip-git-init",
        action="store_true",
        help="Do not initialize a git repository when the destination has no .git directory.",
    )
    return parser.parse_args()


def ensure_path(value: str | None, label: str) -> Path:
    if not value:
        raise SystemExit(f"missing {label}; pass --{label.replace('_', '-')}")
    return Path(value).resolve()


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def reset_destination(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    preserved_git: Path | None = None
    if destination.exists() and (destination / ".git").exists():
        temp_root = Path(tempfile.mkdtemp(prefix="public-export-", dir=destination.parent))
        preserved_git = temp_root / ".git"
        shutil.move(str(destination / ".git"), preserved_git)

    if destination.exists():
        shutil.rmtree(destination, onexc=handle_remove_readonly)

    destination.mkdir(parents=True, exist_ok=True)

    if preserved_git is not None:
        shutil.move(str(preserved_git), destination / ".git")
        with contextlib.suppress(OSError):
            preserved_git.parent.rmdir()


def handle_remove_readonly(function, path, excinfo) -> None:
    path_obj = Path(path)
    with contextlib.suppress(OSError):
        os.chmod(path_obj, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    with contextlib.suppress(OSError):
        os.chmod(path_obj.parent, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
    function(path)


def tracked_files(source_root: Path) -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=source_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return {
        entry.decode("utf-8")
        for entry in result.stdout.split(b"\0")
        if entry
    }


def included_files(source_root: Path, includes: list[str], tracked: set[str]) -> list[str]:
    selected: set[str] = set()

    for relative_path in includes:
        source_path = source_root / relative_path
        if source_path.is_file():
            if relative_path not in tracked:
                raise SystemExit(f"configured include file is not tracked by git: {relative_path}")
            selected.add(relative_path)
            continue

        if source_path.is_dir():
            prefix = f"{relative_path}/"
            matched = {
                path
                for path in tracked
                if path.startswith(prefix) and (source_root / path).is_file()
            }
            if not matched:
                raise SystemExit(f"configured include directory has no tracked files: {relative_path}")
            selected.update(matched)
            continue

        raise SystemExit(f"configured include path does not exist: {relative_path}")

    return sorted(selected)


def copy_file(source_root: Path, destination_root: Path, relative_path: str) -> None:
    source_path = source_root / relative_path
    destination_path = destination_root / relative_path
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, destination_path, follow_symlinks=True)
    destination_path.chmod(0o644)


def remove_path(destination_root: Path, relative_path: str) -> None:
    target = destination_root / relative_path
    if not target.exists():
        return
    if target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink()


def overlay_tree(overlay_root: Path, destination_root: Path) -> None:
    if not overlay_root.exists():
        return

    for source_path in sorted(overlay_root.rglob("*")):
        if source_path.is_dir():
            continue
        relative_path = source_path.relative_to(overlay_root)
        destination_path = destination_root / relative_path
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, destination_path, follow_symlinks=True)
        destination_path.chmod(0o644)


def sanitize_file(path: Path, relative_path: str, config: dict) -> bool:
    if not path.is_file():
        return False

    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    sanitized = original
    for replacement in config.get("literal_replacements", []):
        sanitized = sanitized.replace(replacement["from"], replacement["to"])

    for replacement in config.get("regex_replacements", []):
        sanitized = re.sub(
            replacement["pattern"],
            replacement["replacement"],
            sanitized,
            flags=re.MULTILINE,
        )

    for replacement in config.get("scoped_regex_replacements", []):
        suffixes = replacement.get("suffixes", [])
        paths = replacement.get("paths", [])
        applies = any(relative_path.endswith(suffix) for suffix in suffixes) or any(
            relative_path == scoped_path or relative_path.startswith(f"{scoped_path}/")
            for scoped_path in paths
        )
        if not applies:
            continue
        sanitized = re.sub(
            replacement["pattern"],
            replacement["replacement"],
            sanitized,
            flags=re.MULTILINE,
        )

    if sanitized == original:
        return False

    path.write_text(sanitized, encoding="utf-8")
    return True


def sanitize_tree(destination_root: Path, config: dict) -> list[str]:
    sanitized_files: list[str] = []
    for path in sorted(destination_root.rglob("*")):
        relative_path = str(path.relative_to(destination_root))
        if sanitize_file(path, relative_path, config):
            sanitized_files.append(relative_path)
    return sanitized_files


def refresh_flake_lock(destination_root: Path) -> None:
    flake_path = destination_root / "flake.nix"
    if not flake_path.exists():
        return

    subprocess.run(
        ["nix", "flake", "lock"],
        cwd=destination_root,
        check=True,
    )


def ensure_git_repo(destination_root: Path) -> None:
    if (destination_root / ".git").exists():
        return

    subprocess.run(
        ["git", "init", "--initial-branch", "main"],
        cwd=destination_root,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def stage_git_repo(destination_root: Path) -> None:
    if not (destination_root / ".git").exists():
        return

    subprocess.run(
        ["git", "add", "-A", "."],
        cwd=destination_root,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def main() -> int:
    args = parse_args()
    source_root = Path(args.source).resolve()
    destination_root = Path(args.destination).resolve()
    config_path = ensure_path(args.config, "config")
    overlay_root = ensure_path(args.overlay, "overlay")
    config = load_config(config_path)

    includes = config.get("include_paths", [])
    excludes = config.get("exclude_paths", [])
    tracked = tracked_files(source_root)
    files_to_copy = included_files(source_root, includes, tracked)

    if args.dry_run:
        print("Would export these paths:")
        for relative_path in includes:
            print(f"  include {relative_path}")
        print(f"  tracked files selected: {len(files_to_copy)}")
        for relative_path in excludes:
            print(f"  exclude {relative_path}")
        if overlay_root.exists():
            for source_path in sorted(overlay_root.rglob("*")):
                if source_path.is_file():
                    print(f"  overlay {source_path.relative_to(overlay_root)}")
        print("  sanitize copied text files")
        if not args.skip_lock_refresh:
            print("  refresh flake.lock")
        return 0

    reset_destination(destination_root)

    for relative_path in files_to_copy:
        copy_file(source_root, destination_root, relative_path)

    for relative_path in excludes:
        remove_path(destination_root, relative_path)

    overlay_tree(overlay_root, destination_root)
    sanitized_files = sanitize_tree(destination_root, config)

    if not args.skip_lock_refresh:
        try:
            refresh_flake_lock(destination_root)
        except FileNotFoundError:
            print("warning: `nix` was not found; skipped flake.lock refresh", file=sys.stderr)
        except subprocess.CalledProcessError as exc:
            print(
                f"warning: `nix flake lock` failed with exit code {exc.returncode}; "
                "review the destination and refresh the lock manually",
                file=sys.stderr,
            )

    if not args.skip_git_init:
        try:
            ensure_git_repo(destination_root)
            stage_git_repo(destination_root)
        except FileNotFoundError:
            print("warning: `git` was not found; skipped repository initialization", file=sys.stderr)
        except subprocess.CalledProcessError as exc:
            print(
                f"warning: git repository preparation failed with exit code {exc.returncode}; "
                "initialize or stage the destination repository manually",
                file=sys.stderr,
            )

    print(f"Exported public mirror to {destination_root}")
    if sanitized_files:
        print("Sanitized files:")
        for relative_path in sanitized_files:
            print(f"  {relative_path}")
    else:
        print("No text replacements were needed.")

    print("Next:")
    print(f"  cd {destination_root}")
    print("  git status --short")
    print("  git diff --stat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
