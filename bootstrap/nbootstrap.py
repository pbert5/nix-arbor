#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(os.environ.get("COPILOT_BOOTSTRAP_SCRIPT_DIR", Path(__file__).resolve().parent)).resolve()
LIVE_INSTALLER_SCRIPT = SCRIPT_DIR / "live-installer.py"
BOOTSTRAP_VALIDATE_SCRIPT = SCRIPT_DIR / "bootstrap-validate.py"
YGG_BOOTSTRAP_SCRIPT = SCRIPT_DIR / "yggdrasil-bootstrap.py"


def run(cmd, *, cwd=None, input_text=None, capture_output=False, check=True):
    return subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def nix_eval_json(file_path: Path, apply_expr: str | None = None):
    cmd = ["nix", "eval", "--json", "--file", str(file_path)]
    if apply_expr is not None:
        cmd.extend(["--apply", apply_expr])
    result = run(cmd, capture_output=True)
    return json.loads(result.stdout)


def resolve_bootstrap_connection(*, flake_path: Path, host: str, target: str | None, ssh_user: str | None):
    bootstrap_path = flake_path / "inventory" / "host-bootstrap.nix"
    bootstrap_metadata = nix_eval_json(bootstrap_path)
    bootstrap_entry = bootstrap_metadata.get(host, {})

    resolved_target = target or bootstrap_entry.get("targetHost")
    if resolved_target is None:
        raise SystemExit(
            f"Host '{host}' has no bootstrap target configured. Pass --target or set inventory/host-bootstrap.nix."
        )

    resolved_ssh_user = ssh_user or bootstrap_entry.get("sshUser") or "root"
    return bootstrap_entry, resolved_target, resolved_ssh_user


def build_ssh_command(*, identity_file: str | None, ssh_options, ssh_user: str, target: str, remote_command):
    command = ["ssh"]
    if identity_file is not None:
        command.extend(["-i", identity_file])
    for ssh_option in ssh_options:
        command.extend(["-o", ssh_option])
    command.append(f"{ssh_user}@{target}")
    command.extend(remote_command)
    return command


def run_ssh_reachability_check(
    *,
    identity_file: str | None,
    ssh_options,
    ssh_user: str,
    target: str,
):
    command = build_ssh_command(
        identity_file=identity_file,
        ssh_options=ssh_options,
        ssh_user=ssh_user,
        target=target,
        remote_command=["sh", "-c", "hostname && whoami"],
    )
    run(command)


def forward_to_yggdrasil_bootstrap(arguments):
    cmd = [sys.executable, str(YGG_BOOTSTRAP_SCRIPT), *arguments]
    raise SystemExit(run(cmd, check=False).returncode)


def forward_to_live_installer(arguments):
    cmd = [sys.executable, str(LIVE_INSTALLER_SCRIPT), *arguments]
    raise SystemExit(run(cmd, check=False).returncode)


def forward_to_bootstrap_validate(arguments):
    cmd = [sys.executable, str(BOOTSTRAP_VALIDATE_SCRIPT), *arguments]
    raise SystemExit(run(cmd, check=False).returncode)


def handle_installer_build(args):
    forwarded = [
        "build",
        "--flake",
        args.flake,
        "--attribute",
        args.attribute,
        "--out-link",
        args.out_link,
    ]
    if args.no_link:
        forwarded.append("--no-link")
    if args.print_image_path:
        forwarded.append("--print-image-path")
    forward_to_live_installer(forwarded)


def handle_installer_write(args):
    forwarded = [
        "write",
        "--device",
        args.device,
        "--flake",
        args.flake,
        "--attribute",
        args.attribute,
        "--out-link",
        args.out_link,
    ]
    if args.image is not None:
        forwarded.extend(["--image", args.image])
    forward_to_live_installer(forwarded)


def add_common_enroll_arguments(parser):
    parser.add_argument("--host", required=True, help="Inventory host name to update")
    parser.add_argument("--target", help="Bootstrap SSH target, usually an IP or resolvable host")
    parser.add_argument("--flake", default=".", help="Path to the flake checkout to update")
    parser.add_argument("--ssh-user", help="SSH user for bootstrap access")
    parser.add_argument("--identity-file", help="Optional SSH identity file to use for the bootstrap connection")
    parser.add_argument(
        "--ssh-option",
        action="append",
        default=[],
        help="Additional -o SSH option, may be specified multiple times",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print the discovered identity without rewriting inventory")
    parser.add_argument(
        "--deployment-transport",
        choices=["bootstrap", "privateYggdrasil"],
        help="Update the host bootstrap metadata to prefer this deployment transport after enrollment",
    )
    parser.add_argument(
        "--deployment-tag",
        action="append",
        default=[],
        help="Add a deployment tag in inventory/host-bootstrap.nix, may be specified multiple times",
    )
    parser.add_argument("--operator-capable", action="store_true", help="Mark the host as an operator-capable machine in inventory/host-bootstrap.nix")
    parser.add_argument("--commit", action="store_true", help="Commit the inventory updates after enrollment")
    parser.add_argument("--commit-message", help="Override the default git commit message used with --commit")
    parser.add_argument(
        "--deploy-tool",
        choices=["deploy-rs", "colmena"],
        help="Optionally deploy the enrolled host after updating inventory",
    )
    parser.add_argument(
        "--deploy-peers",
        action="store_true",
        help="When used with --deploy-tool, also deploy the enrolled host's declared private Ygg peers so trust changes propagate",
    )


def build_yggdrasil_bootstrap_arguments(args):
    forwarded = [
        "--host",
        args.host,
        "--flake",
        args.flake,
    ]

    if args.target is not None:
        forwarded.extend(["--target", args.target])
    if args.ssh_user is not None:
        forwarded.extend(["--ssh-user", args.ssh_user])
    if args.identity_file is not None:
        forwarded.extend(["--identity-file", args.identity_file])
    for ssh_option in args.ssh_option:
        forwarded.extend(["--ssh-option", ssh_option])
    if args.dry_run:
        forwarded.append("--dry-run")
    if args.deployment_transport is not None:
        forwarded.extend(["--deployment-transport", args.deployment_transport])
    for deployment_tag in args.deployment_tag:
        forwarded.extend(["--deployment-tag", deployment_tag])
    if args.operator_capable:
        forwarded.append("--operator-capable")
    if args.commit:
        forwarded.append("--commit")
    if args.commit_message is not None:
        forwarded.extend(["--commit-message", args.commit_message])
    if args.deploy_tool is not None:
        forwarded.extend(["--deploy-tool", args.deploy_tool])
    if args.deploy_peers:
        forwarded.append("--deploy-peers")

    return forwarded


def handle_host_enroll(args):
    forward_to_yggdrasil_bootstrap(build_yggdrasil_bootstrap_arguments(args))


def handle_host_bootstrap(args):
    flake_path = Path(args.flake).expanduser().resolve()
    bootstrap_entry, resolved_target, resolved_ssh_user = resolve_bootstrap_connection(
        flake_path=flake_path,
        host=args.host,
        target=args.target,
        ssh_user=args.ssh_user,
    )

    identity_file = args.identity_file or bootstrap_entry.get("identityFile")

    print(
        json.dumps(
            {
                "bootstrap": {
                    "host": args.host,
                    "targetHost": resolved_target,
                    "sshUser": resolved_ssh_user,
                    "identityFile": identity_file,
                }
            },
            indent=2,
            sort_keys=True,
        )
    )

    if not args.skip_ssh_check:
        run_ssh_reachability_check(
            identity_file=identity_file,
            ssh_options=args.ssh_option,
            ssh_user=resolved_ssh_user,
            target=resolved_target,
        )

    args.target = resolved_target
    args.ssh_user = resolved_ssh_user
    args.identity_file = identity_file

    forward_to_yggdrasil_bootstrap(build_yggdrasil_bootstrap_arguments(args))


def handle_validate(args):
    forwarded = [
        "--flake",
        args.flake,
    ]
    if args.json:
        forwarded.append("--json")
    forward_to_bootstrap_validate(forwarded)


def main():
    parser = argparse.ArgumentParser(
        description="Unified bootstrap entrypoint for building the live installer and enrolling hosts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    installer_parser = subparsers.add_parser("installer", help="Build or write the live installer image")
    installer_subparsers = installer_parser.add_subparsers(dest="installer_command", required=True)

    installer_build_parser = installer_subparsers.add_parser("build", help="Build the live installer image")
    installer_build_parser.add_argument("--flake", default=".", help="Flake reference to build from")
    installer_build_parser.add_argument("--attribute", default="live-installer-iso", help="Flake package attribute for the installer image")
    installer_build_parser.add_argument("--out-link", default="result-live-installer", help="Symlink path to create for the build result")
    installer_build_parser.add_argument("--no-link", action="store_true", help="Do not create an output symlink")
    installer_build_parser.add_argument("--print-image-path", action="store_true", help="Print only the resolved image file path")
    installer_build_parser.set_defaults(func=handle_installer_build)

    installer_write_parser = installer_subparsers.add_parser("write", help="Write the live installer image to a USB device")
    installer_write_parser.add_argument("--device", required=True, help="Block device to overwrite, such as /dev/sdX")
    installer_write_parser.add_argument("--image", help="Prebuilt .iso or .img path. If omitted, the installer is built first.")
    installer_write_parser.add_argument("--flake", default=".", help="Flake reference to build from when --image is omitted")
    installer_write_parser.add_argument("--attribute", default="live-installer-iso", help="Flake package attribute for the installer image")
    installer_write_parser.add_argument("--out-link", default="result-live-installer", help="Symlink path to create for the build result when --image is omitted")
    installer_write_parser.set_defaults(func=handle_installer_write)

    validate_parser = subparsers.add_parser("validate", help="Validate bootstrap inventory, leader access, and deploy targets")
    validate_parser.add_argument("--flake", default=".", help="Path to the flake checkout to validate")
    validate_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    validate_parser.set_defaults(func=handle_validate)

    host_parser = subparsers.add_parser("host", help="Enroll or bootstrap a target host")
    host_subparsers = host_parser.add_subparsers(dest="host_command", required=True)

    host_enroll_parser = host_subparsers.add_parser("enroll", help="Run the host identity enrollment flow")
    add_common_enroll_arguments(host_enroll_parser)
    host_enroll_parser.set_defaults(func=handle_host_enroll)

    host_bootstrap_parser = host_subparsers.add_parser(
        "bootstrap",
        help="Run the common bootstrap flow: resolve connection data, verify SSH, then enroll and optionally deploy",
    )
    add_common_enroll_arguments(host_bootstrap_parser)
    host_bootstrap_parser.add_argument(
        "--skip-ssh-check",
        action="store_true",
        help="Skip the initial hostname/whoami SSH reachability check",
    )
    host_bootstrap_parser.set_defaults(func=handle_host_bootstrap)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
