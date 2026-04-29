#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


SKIP_PACKAGE_ENUMERATION = {"nixpkgs", "nixpkgs-unstable"}
PACKAGE_NAME_LIMIT = 200
DEFAULT_EXTRA_GIT_REPOS = [
    {
        "name": "nix",
        "source": "default-extra",
        "url": "https://github.com/NixOS/nix.git",
    }
]
DEFAULT_ISO_SYSTEM = "x86_64-linux"


def run(
    command: list[str],
    *,
    capture_output: bool = True,
    check: bool = True,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    effective_timeout = None if timeout is None or timeout <= 0 else timeout
    return subprocess.run(
        command,
        check=check,
        capture_output=capture_output,
        text=True,
        timeout=effective_timeout,
    )


def run_json(command: list[str], *, timeout: int | None = None) -> Any:
    completed = run(command, timeout=timeout)
    return json.loads(completed.stdout)


def ensure_snapshot_argv(argv: list[str]) -> list[str]:
    if not argv or argv[0].startswith("-"):
        return ["snapshot", *argv]
    return argv


def sanitize_name(name: str) -> str:
    sanitized = name.removesuffix(".git")
    for old, new in [("/", "-"), (":", "-"), (" ", "-")]:
        sanitized = sanitized.replace(old, new)
    return sanitized


def unique_by(items: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for item in items:
        seen[item[key]] = item
    return list(seen.values())


def node_type(node: dict[str, Any]) -> str | None:
    return node.get("locked", {}).get("type") or node.get("original", {}).get("type")


def node_field(node: dict[str, Any], *path: str) -> Any:
    current: Any = node.get("locked", {})
    for key in path:
        if not isinstance(current, dict) or key not in current:
            current = None
            break
        current = current[key]
    if current is not None:
        return current

    current = node.get("original", {})
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def normalize_git_url(url: str) -> str:
    normalized = url.removeprefix("git+").split("?", 1)[0]
    if normalized.startswith("user@example.com:"):
        return f"https://github.com/{normalized.split(':', 1)[1]}"
    if normalized.startswith("ssh://user@example.com/"):
        return f"https://github.com/{normalized.removeprefix('ssh://user@example.com/')}"
    if normalized.startswith("user@example.com:"):
        return f"https://gitlab.com/{normalized.split(':', 1)[1]}"
    if normalized.startswith("ssh://user@example.com/"):
        return f"https://gitlab.com/{normalized.removeprefix('ssh://user@example.com/')}"
    return normalized


def git_repo_from_node(node_name: str, node: dict[str, Any]) -> dict[str, Any] | None:
    input_type = node_type(node)
    owner = node_field(node, "owner")
    repo = node_field(node, "repo")
    host = node_field(node, "host")
    ref = node_field(node, "ref")
    rev = node_field(node, "rev")
    raw_url = node_field(node, "url")

    if input_type == "github" and owner and repo:
        url = f"https://github.com/{owner}/{repo}.git"
    elif input_type == "gitlab" and owner and repo:
        url = f"https://{host or 'gitlab.com'}/{owner}/{repo}.git"
    elif input_type == "sourcehut" and owner and repo:
        url = f"https://{host or 'git.sr.ht'}/~{owner}/{repo}"
    elif input_type == "git" and raw_url:
        url = normalize_git_url(raw_url)
    else:
        return None

    return {
        "inputName": node_name,
        "name": sanitize_name(repo or node_name),
        "ref": ref,
        "rev": rev,
        "source": "flake-lock",
        "type": input_type,
        "url": url,
    }


def path_input_from_node(node_name: str, node: dict[str, Any]) -> dict[str, Any] | None:
    input_type = node_type(node)
    source_path = node.get("original", {}).get("path") or node_field(node, "path")
    if input_type != "path" or not source_path:
        return None
    return {
        "inputName": node_name,
        "lockedPath": node.get("locked", {}).get("path"),
        "name": sanitize_name(node_name),
        "path": source_path,
        "source": "flake-lock",
    }


def non_root_nodes(metadata: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    locks = metadata.get("locks", {})
    root_name = locks.get("root")
    nodes = locks.get("nodes", {})
    return [(node_name, node) for node_name, node in nodes.items() if node_name != root_name]


def git_repos_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    repos = [
        repo
        for node_name, node in non_root_nodes(metadata)
        for repo in [git_repo_from_node(node_name, node)]
        if repo is not None
    ]
    return sorted(unique_by(repos, "url"), key=lambda repo: repo["name"])


def path_inputs_from_metadata(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    path_inputs = [
        path_input
        for node_name, node in non_root_nodes(metadata)
        for path_input in [path_input_from_node(node_name, node)]
        if path_input is not None
    ]
    return sorted(unique_by(path_inputs, "path"), key=lambda path_input: path_input["name"])


def previous_release_branch(branch: str | None) -> str | None:
    if not branch:
        return None
    match = re.fullmatch(r"nixos-(\d{2})\.(\d{2})", branch)
    if not match:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    if month == 11:
        previous = (year, 5)
    elif month == 5:
        previous = (year - 1, 11)
    else:
        return None
    return f"nixos-{previous[0]:02d}.{previous[1]:02d}"


def default_iso_channels_from_metadata(metadata: dict[str, Any]) -> list[str]:
    locks = metadata.get("locks", {})
    nodes = locks.get("nodes", {})
    root_name = locks.get("root")
    root_node = nodes.get(root_name, {}) if root_name else {}
    nixpkgs_node_name = root_node.get("inputs", {}).get("nixpkgs")
    nixpkgs_node = nodes.get(nixpkgs_node_name, {}) if nixpkgs_node_name else {}
    current_branch = node_field(nixpkgs_node, "ref")
    branches = [branch for branch in [current_branch, previous_release_branch(current_branch)] if branch]
    return list(dict.fromkeys(branches))


def local_flake_path(flake_ref: str) -> Path | None:
    candidate = Path(flake_ref).expanduser()
    if candidate.exists():
        return candidate.resolve()
    return None


def extract_store_paths(payload: Any) -> set[str]:
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and value.startswith("/nix/store/"):
            found.add(value)

    visit(payload)
    return found


def make_copy_name(path: str, seen: dict[str, int]) -> str:
    base = Path(path).name.replace("/", "_")
    index = seen.get(base, 0)
    seen[base] = index + 1
    return base if index == 0 else f"{base}-{index}"


def copy_source(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        run(["rsync", "-a", "--delete", f"{src}/", f"{dest}/"], capture_output=True)
    else:
        if dest.exists():
            dest.unlink()
        shutil.copy2(src, dest)


def copy_tree(src: Path, dest: Path, *, excludes: list[str] | None = None) -> None:
    excludes = excludes or []
    dest.parent.mkdir(parents=True, exist_ok=True)
    command = ["rsync", "-a", "--delete"]
    for pattern in excludes:
        command.extend(["--exclude", pattern])
    command.extend([f"{src}/", f"{dest}/"])
    run(command, capture_output=True)


def download_url(url: str, destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
        content_type = response.headers.get("Content-Type")
    return {
        "url": url,
        "destination": str(destination),
        "contentType": content_type,
        "size": destination.stat().st_size,
    }


def download_live_install_tools(output_root: Path, iso_channels: list[str], iso_system: str) -> list[dict[str, Any]]:
    if not iso_channels:
        return []

    isos_root = output_root / "isos"
    downloaded: list[dict[str, Any]] = []
    for channel in iso_channels:
        base = f"https://channels.nixos.org/{channel}"
        iso_name = f"latest-nixos-minimal-{iso_system}.iso"
        checksum_name = f"{iso_name}.sha256"
        channel_root = isos_root / channel

        print(f"[insurance] downloading live install tools for {channel}")
        iso_result = download_url(f"{base}/{iso_name}", channel_root / iso_name)
        checksum_result = download_url(f"{base}/{checksum_name}", channel_root / checksum_name)
        downloaded.append(
            {
                "channel": channel,
                "system": iso_system,
                "iso": iso_result,
                "checksum": checksum_result,
            }
        )

    return downloaded


def sync_git_repo(source: str, clone_dir: Path, bundle_file: Path) -> None:
    clone_dir.parent.mkdir(parents=True, exist_ok=True)
    bundle_file.parent.mkdir(parents=True, exist_ok=True)

    if not (clone_dir / ".git").exists():
        if clone_dir.exists():
            shutil.rmtree(clone_dir)
        run(["git", "clone", source, str(clone_dir)], timeout=0)

    run(["git", "-C", str(clone_dir), "remote", "set-url", "origin", source], check=False)
    fetch = run(
        [
            "git",
            "-C",
            str(clone_dir),
            "fetch",
            "--force",
            "--prune",
            "--tags",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
        ],
        check=False,
        timeout=0,
    )
    if fetch.returncode != 0:
        run(
            ["git", "-C", str(clone_dir), "fetch", "--force", "--prune", "--tags", "origin"],
            timeout=0,
        )

    shallow = run(
        ["git", "-C", str(clone_dir), "rev-parse", "--is-shallow-repository"],
        check=False,
        timeout=0,
    )
    if shallow.stdout.strip() == "true":
        run(["git", "-C", str(clone_dir), "fetch", "--unshallow", "origin"], check=False, timeout=0)

    run(["git", "-C", str(clone_dir), "remote", "set-head", "origin", "-a"], check=False, timeout=0)
    temp_bundle = bundle_file.with_suffix(bundle_file.suffix + ".tmp")
    run(["git", "-C", str(clone_dir), "bundle", "create", str(temp_bundle), "--all"], timeout=0)
    temp_bundle.replace(bundle_file)


def locked_ref(locked: dict[str, Any]) -> str | None:
    input_type = locked.get("type")
    if input_type == "github":
        owner = locked.get("owner")
        repo = locked.get("repo")
        rev = locked.get("rev")
        if owner and repo and rev:
            return f"github:{owner}/{repo}/{rev}"
    if input_type == "path":
        path = locked.get("path")
        if path:
            return f"path:{path}"
    if input_type == "git":
        url = locked.get("url")
        if url:
            query = []
            if locked.get("rev"):
                query.append(f"rev={locked['rev']}")
            if locked.get("ref"):
                query.append(f"ref={locked['ref']}")
            suffix = f"?{'&'.join(query)}" if query else ""
            return f"git+{url}{suffix}"
    if input_type == "tarball":
        return locked.get("url")
    return None


def summary_names(mapping: Any, *, limit: int = PACKAGE_NAME_LIMIT) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {"count": 0, "names": [], "truncated": False}
    names = sorted(mapping.keys())
    return {
        "count": len(names),
        "names": names[:limit],
        "truncated": len(names) > limit,
    }


def summarise_flake_show(payload: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key in ["packages", "apps", "checks", "devShells"]:
        section = payload.get(key)
        if isinstance(section, dict):
            summary[key] = {system: summary_names(values) for system, values in section.items()}
    for key in ["nixosModules", "homeModules", "overlays", "templates"]:
        if isinstance(payload.get(key), dict):
            summary[key] = summary_names(payload[key])
    return summary


def enumerate_node_outputs(
    root_ref: str,
    metadata: dict[str, Any],
    *,
    include_large_package_sets: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    outputs: dict[str, Any] = {}
    errors: list[str] = []
    nodes = metadata.get("locks", {}).get("nodes", {})
    root_name = metadata.get("locks", {}).get("root")

    candidates: list[tuple[str, str]] = [(root_name or "root", root_ref)]
    for node_name, node in nodes.items():
        if node_name == root_name:
            continue
        if node_name in SKIP_PACKAGE_ENUMERATION and not include_large_package_sets:
            outputs[node_name] = {"skipped": "package enumeration intentionally skipped for very large input"}
            continue
        if node.get("flake") is False:
            continue
        ref = locked_ref(node.get("locked", {}))
        if ref:
            candidates.append((node_name, ref))

    for node_name, ref in candidates:
        try:
            show_json = run_json(["nix", "flake", "show", "--json", ref], timeout=300)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{node_name}: {exc}")
            continue
        outputs[node_name] = {
            "ref": ref,
            "summary": summarise_flake_show(show_json),
        }

    return outputs, errors


def parse_extra_git_repo(spec: str) -> dict[str, Any]:
    if "=" not in spec:
        raise SystemExit(f"Invalid --extra-git-repo '{spec}'. Use name=url.")
    name, url = spec.split("=", 1)
    name = name.strip()
    url = url.strip()
    if not name or not url:
        raise SystemExit(f"Invalid --extra-git-repo '{spec}'. Use name=url.")
    return {
        "name": sanitize_name(name),
        "source": "cli-extra",
        "url": normalize_git_url(url),
    }


def snapshot(args: argparse.Namespace) -> int:
    flake_ref = args.flake
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    local_source_root = local_flake_path(flake_ref)

    print(f"[insurance] reading flake metadata for {flake_ref}")
    metadata = run_json(["nix", "flake", "metadata", "--json", flake_ref], timeout=300)
    metadata_path = output_root / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")

    git_repos = git_repos_from_metadata(metadata)
    if not args.no_default_extra_repos:
        git_repos.extend(DEFAULT_EXTRA_GIT_REPOS)
    if args.extra_git_repo:
        git_repos.extend([parse_extra_git_repo(spec) for spec in args.extra_git_repo])
    git_repos = sorted(unique_by(git_repos, "url"), key=lambda repo: repo["name"])

    path_inputs = path_inputs_from_metadata(metadata)
    snapshots: list[dict[str, Any]] = []
    if local_source_root is not None:
        snapshots.append(
            {
                "name": sanitize_name(local_source_root.name or "flake"),
                "path": str(local_source_root),
                "source": "working-tree",
            }
        )
    snapshots.extend(path_inputs)

    iso_channels = default_iso_channels_from_metadata(metadata)
    live_install_tools: list[dict[str, Any]] = []
    if not args.skip_live_install_tools:
        live_install_tools = download_live_install_tools(output_root, iso_channels, args.iso_system)

    snapshot_copies: list[dict[str, Any]] = []
    if args.copy_snapshots:
        snapshots_root = output_root / "snapshots"
        for snapshot_spec in snapshots:
            source_path = Path(snapshot_spec["path"]).expanduser()
            if not source_path.exists():
                continue
            destination = snapshots_root / snapshot_spec["name"]
            excludes = [".git"]
            if local_source_root is not None and source_path.resolve() == local_source_root and output_root.parent == source_path.resolve():
                excludes.append(output_root.name)
            print(f"[insurance] snapshotting {source_path} -> {destination}")
            copy_tree(source_path, destination, excludes=excludes)
            snapshot_copies.append(
                {
                    "source": str(source_path.resolve()),
                    "destination": str(destination),
                    "kind": snapshot_spec.get("source", "snapshot"),
                }
            )

    git_mirrors: list[dict[str, Any]] = []
    if not args.skip_git_mirrors:
        repos_root = output_root / "repos"
        bundles_root = output_root / "bundles"
        for repo in git_repos:
            clone_dir = repos_root / repo["name"]
            bundle_file = bundles_root / f"{repo['name']}.bundle"
            print(f"[insurance] mirroring git repo {repo['url']}")
            sync_git_repo(repo["url"], clone_dir, bundle_file)
            git_mirrors.append(
                {
                    **repo,
                    "bundle": str(bundle_file),
                    "clone": str(clone_dir),
                }
            )

    archive_payload: Any = {}
    archive_store_paths: list[str] = []
    if not args.skip_archive:
        print(f"[insurance] archiving flake inputs for {flake_ref}")
        archive_payload = run_json(["nix", "flake", "archive", "--json", flake_ref], timeout=0)
        (output_root / "archive.json").write_text(json.dumps(archive_payload, indent=2, sort_keys=True) + "\n")
        archive_store_paths = sorted(extract_store_paths(archive_payload))

    copied_sources: list[dict[str, Any]] = []
    if args.copy_sources and archive_store_paths:
        sources_root = output_root / "sources"
        seen_names: dict[str, int] = {}
        for path in archive_store_paths:
            src = Path(path)
            if not src.exists():
                continue
            destination = sources_root / make_copy_name(path, seen_names)
            print(f"[insurance] copying {src} -> {destination}")
            copy_source(src, destination)
            copied_sources.append({"source": path, "destination": str(destination)})

    output_inventory: dict[str, Any] = {}
    output_errors: list[str] = []
    if not args.skip_packages:
        print("[insurance] enumerating flake outputs")
        output_inventory, output_errors = enumerate_node_outputs(
            flake_ref,
            metadata,
            include_large_package_sets=args.include_large_package_sets,
        )
        (output_root / "flake-outputs.json").write_text(json.dumps(output_inventory, indent=2, sort_keys=True) + "\n")

    closure_info: dict[str, Any] | None = None
    installable = args.installable
    if args.nixos_host and not installable:
        installable = f"{flake_ref}#nixosConfigurations.{args.nixos_host}.config.system.build.toplevel"

    if installable:
        print(f"[insurance] building installable {installable}")
        build_out = run(["nix", "build", "--no-link", "--print-out-paths", installable], timeout=0)
        built_paths = [line for line in build_out.stdout.splitlines() if line.strip()]
        closure_paths = run_json(["nix", "path-info", "--json", "-r", *built_paths], timeout=0)
        closure_info = {
            "installable": installable,
            "builtPaths": built_paths,
            "closure": closure_paths,
        }
        (output_root / "closure.json").write_text(json.dumps(closure_info, indent=2, sort_keys=True) + "\n")

        if args.copy_store:
            store_root = output_root / "store-export"
            store_root.mkdir(parents=True, exist_ok=True)
            print(f"[insurance] exporting closure to {store_root}")
            run(["nix", "copy", "--to", f"file://{store_root}", *built_paths], capture_output=True, timeout=0)
            closure_info["storeExport"] = str(store_root)
            (output_root / "closure.json").write_text(json.dumps(closure_info, indent=2, sort_keys=True) + "\n")

    manifest = {
        "flake": flake_ref,
        "historicalReferenceCommit": "51128731525cdc8aedbdcec17f6d6816310d1e9f",
        "metadataPath": str(metadata_path),
        "isoChannels": iso_channels,
        "liveInstallTools": live_install_tools,
        "gitRepos": git_repos,
        "gitMirrorCount": len(git_mirrors),
        "gitMirrors": git_mirrors,
        "pathInputs": path_inputs,
        "snapshotCount": len(snapshot_copies),
        "snapshots": snapshot_copies,
        "archiveStorePathCount": len(archive_store_paths),
        "copiedSourceCount": len(copied_sources),
        "copiedSources": copied_sources,
        "flakeOutputs": output_inventory,
        "outputEnumerationErrors": output_errors,
        "closure": closure_info,
    }
    (output_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print(f"[insurance] wrote manifest to {output_root / 'manifest.json'}")
    print(f"[insurance] downloaded live install tools: {len(live_install_tools)}")
    print(f"[insurance] mirrored git repos: {len(git_mirrors)}")
    print(f"[insurance] copied snapshots: {len(snapshot_copies)}")
    print(f"[insurance] archived store paths: {len(archive_store_paths)}")
    print(f"[insurance] copied sources: {len(copied_sources)}")
    if output_inventory:
        print(f"[insurance] enumerated outputs for {len(output_inventory)} flakes")
    if closure_info is not None:
        print(f"[insurance] captured closure for {installable}")
    if output_errors:
        print("[insurance] output enumeration errors:")
        for error in output_errors:
            print(f"  - {error}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mirror flake inputs and optional build closures for offline-ish rebuild insurance."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    snapshot_parser = subparsers.add_parser("snapshot", help="Archive sources and optional build closures for a flake.")
    snapshot_parser.add_argument("--flake", default=".", help="Flake ref or path to snapshot.")
    snapshot_parser.add_argument(
        "--output-root",
        default="./insurance-output",
        help="Directory where metadata, copied sources, and manifests are written.",
    )
    snapshot_parser.add_argument(
        "--skip-git-mirrors",
        action="store_true",
        help="Skip refreshing git clones and rolling bundle files for lock-discovered repos.",
    )
    snapshot_parser.add_argument(
        "--skip-live-install-tools",
        action="store_true",
        help="Skip downloading NixOS live installer media for the derived release channels.",
    )
    snapshot_parser.add_argument(
        "--iso-system",
        default=DEFAULT_ISO_SYSTEM,
        help="Installer ISO system suffix, for example x86_64-linux.",
    )
    snapshot_parser.add_argument(
        "--nixos-host",
        help="Shortcut for capturing .#nixosConfigurations.<host>.config.system.build.toplevel.",
    )
    snapshot_parser.add_argument("--installable", help="Explicit installable to build and capture a closure for.")
    snapshot_parser.add_argument("--copy-store", action="store_true", help="Export the built closure into a local file:// Nix store mirror.")
    snapshot_parser.add_argument("--skip-archive", action="store_true", help="Skip `nix flake archive` and source copying.")
    snapshot_parser.add_argument("--skip-packages", action="store_true", help="Skip `nix flake show` enumeration for the root and referenced flakes.")
    snapshot_parser.add_argument(
        "--extra-git-repo",
        action="append",
        default=[],
        help="Add an extra repo to mirror in the form name=url.",
    )
    snapshot_parser.add_argument(
        "--no-default-extra-repos",
        action="store_true",
        help="Do not include the default extra repo set recovered from the earlier offline-insurance branch.",
    )
    snapshot_parser.add_argument(
        "--no-copy-sources",
        action="store_false",
        dest="copy_sources",
        help="Archive inputs but keep them in the Nix store instead of copying them into the output directory.",
    )
    snapshot_parser.add_argument(
        "--no-copy-snapshots",
        action="store_false",
        dest="copy_snapshots",
        help="Skip plain working-tree/path-input snapshots and only keep git mirrors plus flake archive data.",
    )
    snapshot_parser.add_argument(
        "--include-large-package-sets",
        action="store_true",
        help="Also enumerate very large package surfaces such as nixpkgs inputs.",
    )
    snapshot_parser.set_defaults(func=snapshot, copy_sources=True, copy_snapshots=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args(ensure_snapshot_argv(sys.argv[1:]))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
