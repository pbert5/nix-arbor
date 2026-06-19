#!/usr/bin/env python3

import argparse
import json
import re
import subprocess
from pathlib import Path


DATE_STAMP_RE = re.compile(r".*_[0-9]{8}([^/]*)")
LEADER_KEY_RE = re.compile(r"^(?P<host>.+)-root-deployer\.txt$")


def run(cmd, *, cwd=None):
    return subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
    )


def nix_eval_json_file(path: Path):
    expr = (
        "let value = import "
        + json.dumps(str(path))
        + "; in if builtins.isFunction value then value {} else value"
    )
    result = run(["nix", "eval", "--impure", "--json", "--expr", expr])
    return json.loads(result.stdout)


def first_non_null(fallback, values):
    for value in values:
        if value is not None:
            return value
    return fallback


def add_issue(issues, severity: str, message: str):
    issues.append(
        {
            "severity": severity,
            "message": message,
        }
    )


def validate(args):
    flake_path = Path(args.flake).expanduser().resolve()
    inventory_dir = flake_path / "inventory"
    leader_keys_dir = inventory_dir / "keys" / "leaders"
    issues = []
    summaries = []

    hosts = nix_eval_json_file(inventory_dir / "hosts.nix")
    bootstrap = nix_eval_json_file(inventory_dir / "host-bootstrap.nix")
    identities = nix_eval_json_file(inventory_dir / "private-yggdrasil-identities.nix")
    networks = nix_eval_json_file(inventory_dir / "networks.nix")
    try:
        run(["nix", "flake", "show", "--all-systems"], cwd=flake_path)
    except subprocess.CalledProcessError as exc:
        add_issue(
            issues,
            severity="error",
            message=f"Flake evaluation failed: {exc.stderr.strip() or exc.stdout.strip() or 'nix flake show failed.'}",
        )
        errors = [issue for issue in issues if issue["severity"] == "error"]
        payload = {
            "flake": str(flake_path),
            "ok": False,
            "errors": errors,
            "warnings": [ ],
            "hosts": [ ],
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print("Bootstrap validation summary")
            print(f"- flake: {flake_path}")
            print("- errors: 1")
            print("")
            print("Errors")
            for issue in errors:
                print(f"- {issue['message']}")
        return 1

    exported_hosts = sorted(name for name, host in hosts.items() if host.get("exported", True))
    private_ygg_nodes = networks.get("privateYggdrasil", {}).get("nodes", {})
    leader_key_files = sorted(path for path in leader_keys_dir.iterdir() if path.is_file())

    for host_name in exported_hosts:
        host = hosts[host_name]
        bootstrap_entry = bootstrap.get(host_name)
        identity = identities.get(host_name, {})
        transport = (bootstrap_entry or {}).get("deploymentTransport", "bootstrap")
        target_host = (bootstrap_entry or {}).get("targetHost")
        identity_file = (bootstrap_entry or {}).get("identityFile")
        operator_capable = bool((bootstrap_entry or {}).get("operatorCapable", False))
        ygg_address = identity.get("address")
        ygg_public_key = identity.get("publicKey")
        networks_for_host = host.get("networks", [])
        has_private_ygg = "privateYggdrasil" in networks_for_host
        leader_key_file = leader_keys_dir / f"{host_name}-root-deployer.txt"
        private_ygg_node = private_ygg_nodes.get(host_name, {})
        ygg_target_host = private_ygg_node.get("deployHost") or private_ygg_node.get("address")
        preferred_transport_target = host_name if transport == "privateYggdrasil" and ygg_target_host is not None else None
        deploy_hostname = first_non_null(
            host_name,
            [
                preferred_transport_target,
                target_host,
                private_ygg_node.get("deployHost"),
                private_ygg_node.get("endpointHost"),
                host_name,
            ],
        )

        if bootstrap_entry is None:
            add_issue(issues, "error", f"Exported host '{host_name}' is missing inventory/host-bootstrap.nix metadata.")
            summaries.append(
                {
                    "host": host_name,
                    "transport": "missing",
                    "targetHost": None,
                    "operatorCapable": False,
                    "yggEnrolled": False,
                    "deployHostname": None,
                }
            )
            continue

        if target_host is None:
            add_issue(issues, "error", f"Host '{host_name}' has no bootstrap targetHost.")

        if identity_file and DATE_STAMP_RE.match(identity_file):
            add_issue(
                issues,
                "error",
                f"Host '{host_name}' uses dated identityFile '{identity_file}'. Use a stable alias such as /home/example/.ssh/deploy_rsa.",
            )

        if identity_file and not Path(identity_file).expanduser().exists():
            add_issue(
                issues,
                "warning",
                f"Host '{host_name}' points at local identityFile '{identity_file}', but it does not exist on this machine.",
            )

        if operator_capable and not leader_key_file.exists():
            add_issue(
                issues,
                "error",
                f"Host '{host_name}' is operator-capable but {leader_key_file.relative_to(flake_path)} is missing.",
            )

        if transport == "privateYggdrasil":
            if not has_private_ygg:
                add_issue(
                    issues,
                    "error",
                    f"Host '{host_name}' deploys over privateYggdrasil but does not select the privateYggdrasil network.",
                )
            if ygg_address is None or ygg_public_key is None:
                add_issue(
                    issues,
                    "error",
                    f"Host '{host_name}' deploys over privateYggdrasil but its Ygg identity is incomplete.",
                )
            if deploy_hostname != host_name:
                add_issue(
                    issues,
                    "error",
                    f"Host '{host_name}' deploys over privateYggdrasil but the resolved deploy hostname is '{deploy_hostname}', not the logical host name.",
                )

        if has_private_ygg and host_name not in private_ygg_nodes:
            add_issue(
                issues,
                "error",
                f"Host '{host_name}' selects privateYggdrasil but inventory/networks.nix has no node entry for it.",
            )

        if deploy_hostname is None:
            add_issue(issues, "error", f"Host '{host_name}' does not resolve to any deploy hostname.")

        summaries.append(
            {
                "host": host_name,
                "transport": transport,
                "targetHost": target_host,
                "operatorCapable": operator_capable,
                "yggEnrolled": ygg_address is not None and ygg_public_key is not None,
                "deployHostname": deploy_hostname,
            }
        )

    for host_name in sorted(bootstrap):
        if host_name not in hosts:
            add_issue(issues, "error", f"inventory/host-bootstrap.nix defines unknown host '{host_name}'.")

    for leader_key_file in leader_key_files:
        match = LEADER_KEY_RE.match(leader_key_file.name)
        if match is None:
            add_issue(
                issues,
                "error",
                f"Leader key file '{leader_key_file.relative_to(flake_path)}' does not match '<host>-root-deployer.txt'.",
            )
            continue

        host_name = match.group("host")
        bootstrap_entry = bootstrap.get(host_name, {})
        if host_name not in hosts:
            add_issue(
                issues,
                "error",
                f"Leader key file '{leader_key_file.relative_to(flake_path)}' references unknown host '{host_name}'.",
            )
        elif not bootstrap_entry.get("operatorCapable", False):
            add_issue(
                issues,
                "error",
                f"Leader key file '{leader_key_file.relative_to(flake_path)}' exists, but host '{host_name}' is not marked operatorCapable.",
            )

        if leader_key_file.read_text().strip() == "":
            add_issue(
                issues,
                "error",
                f"Leader key file '{leader_key_file.relative_to(flake_path)}' is empty.",
            )

    errors = [issue for issue in issues if issue["severity"] == "error"]
    warnings = [issue for issue in issues if issue["severity"] == "warning"]
    payload = {
        "flake": str(flake_path),
        "ok": errors == [],
        "errors": errors,
        "warnings": warnings,
        "hosts": summaries,
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("Bootstrap validation summary")
        print(f"- flake: {flake_path}")
        print(f"- exported hosts: {len(exported_hosts)}")
        print(f"- errors: {len(errors)}")
        print(f"- warnings: {len(warnings)}")
        print("")
        for summary in summaries:
            ygg = "yes" if summary["yggEnrolled"] else "no"
            operator = "yes" if summary["operatorCapable"] else "no"
            print(
                f"- {summary['host']}: transport={summary['transport']} target={summary['targetHost']} "
                f"deploy={summary['deployHostname']} yggEnrolled={ygg} operatorCapable={operator}"
            )

        if warnings:
            print("")
            print("Warnings")
            for issue in warnings:
                print(f"- {issue['message']}")

        if errors:
            print("")
            print("Errors")
            for issue in errors:
                print(f"- {issue['message']}")

    return 0 if errors == [] else 1


def main():
    parser = argparse.ArgumentParser(
        description="Validate bootstrap inventory, leader access wiring, and generated deploy targets."
    )
    parser.add_argument("--flake", default=".", help="Path to the flake checkout to validate")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    raise SystemExit(validate(parser.parse_args()))


if __name__ == "__main__":
    main()
