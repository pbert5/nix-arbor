#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path


REMOTE_SCRIPT = r"""#!/usr/bin/env bash
set -euo pipefail

keys_path=/var/lib/yggdrasil/keys.json
keys_dir=$(dirname "$keys_path")
filter_expr='to_entries|map(select(.key|endswith("Key")))|from_entries'

ensure_keys() {
  if [ -e "$keys_path" ]; then
    return 0
  fi

  install -d -m 700 "$keys_dir"

  if command -v yggdrasil >/dev/null 2>&1; then
    if command -v jq >/dev/null 2>&1; then
      yggdrasil -genconf -json | jq "$filter_expr" > "$keys_path"
    else
      nix shell nixpkgs#jq -c bash -lc \
        "yggdrasil -genconf -json | jq '$filter_expr' > '$keys_path'"
    fi
  else
    nix shell nixpkgs#jq nixpkgs#yggdrasil -c bash -lc \
      "yggdrasil -genconf -json | jq '$filter_expr' > '$keys_path'"
  fi

  chmod 600 "$keys_path"
}

read_public_key() {
  if command -v yggdrasil >/dev/null 2>&1; then
    yggdrasil -useconffile "$keys_path" -publickey
  else
    nix shell nixpkgs#yggdrasil -c yggdrasil -useconffile "$keys_path" -publickey
  fi
}

read_address() {
  if command -v yggdrasil >/dev/null 2>&1; then
    yggdrasil -useconffile "$keys_path" -address
  else
    nix shell nixpkgs#yggdrasil -c yggdrasil -useconffile "$keys_path" -address
  fi
}

ensure_keys
public_key="$(read_public_key)"
address="$(read_address)"

printf '{"publicKey":"%s","address":"%s"}\n' "$public_key" "$address"
"""


def run(cmd, *, cwd=None, input_text=None):
    return subprocess.run(
        cmd,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=True,
    )


def nix_eval_json(file_path: Path, apply_expr: str | None = None):
    cmd = ["nix", "eval", "--json", "--file", str(file_path)]
    if apply_expr is not None:
        cmd.extend(["--apply", apply_expr])
    result = run(cmd)
    return json.loads(result.stdout)


def render_bootstrap(node_names, bootstrap_metadata):
    lines = ["{"]
    for node_name in node_names:
        node = bootstrap_metadata.get(node_name, {})
        deployment_tags = node.get("deploymentTags", [])
        deployment_transport = node.get("deploymentTransport", "bootstrap")
        identity_file = node.get("identityFile")
        operator_capable = node.get("operatorCapable", False)
        ssh_user = node.get("sshUser", "root")
        target_host = node.get("targetHost")
        lines.extend(
            [
                f'  "{node_name}" = {{',
                f"    deploymentTags = {json.dumps(deployment_tags)};",
                f"    deploymentTransport = {json.dumps(deployment_transport)};",
                f"    identityFile = {json.dumps(identity_file) if identity_file is not None else 'null'};",
                f"    operatorCapable = {'true' if operator_capable else 'false'};",
                f"    sshUser = {json.dumps(ssh_user)};",
                f"    targetHost = {json.dumps(target_host) if target_host is not None else 'null'};",
                "  };",
                "",
            ]
        )

    if lines[-1] == "":
        lines.pop()
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def render_identities(node_names, identities):
    lines = ["{"]
    for node_name in node_names:
        node = identities.get(node_name, {})
        address = node.get("address")
        public_key = node.get("publicKey")
        lines.extend(
            [
                f'  "{node_name}" = {{',
                f"    address = {json.dumps(address) if address is not None else 'null'};",
                f"    publicKey = {json.dumps(public_key) if public_key is not None else 'null'};",
                "  };",
                "",
            ]
        )

    if lines[-1] == "":
        lines.pop()
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def build_ssh_command(args):
    command = ["ssh"]
    if args.identity_file is not None:
        command.extend(["-i", str(args.identity_file)])
    for ssh_option in args.ssh_option:
        command.extend(["-o", ssh_option])
    command.append(f"{args.ssh_user}@{args.target}")
    command.extend(["bash", "-s", "--"])
    return command


def git_commit(flake_path: Path, files, message: str):
    run(["git", "add", *[str(path) for path in files]], cwd=flake_path)

    try:
        run(["git", "diff", "--cached", "--quiet"], cwd=flake_path)
    except subprocess.CalledProcessError:
        run(["git", "commit", "-m", message], cwd=flake_path)
        return True

    return False


def deploy_hosts(
    *,
    flake_path: Path,
    hosts,
    tool: str,
):
    if hosts == []:
        return

    if tool == "deploy-rs":
        for host in hosts:
            run(["nix", "run", f"{flake_path}#deploy-rs", "--", f".#{host}"], cwd=flake_path)
        return

    if tool == "colmena":
        run(["nix", "run", f"{flake_path}#colmena", "--", "apply", "--on", ",".join(hosts)], cwd=flake_path)
        return

    raise ValueError(f"Unsupported deployment tool: {tool}")


def main():
    parser = argparse.ArgumentParser(
        description="Enroll a host-generated Yggdrasil identity into inventory/private-yggdrasil-identities.nix"
    )
    parser.add_argument("--host", required=True, help="Inventory host name to update")
    parser.add_argument("--target", help="Bootstrap SSH target, usually an IP or resolvable host")
    parser.add_argument(
        "--flake",
        default=".",
        help="Path to the flake checkout to update (default: current directory)",
    )
    parser.add_argument(
        "--ssh-user",
        help="SSH user for bootstrap access (defaults to inventory metadata or root)",
    )
    parser.add_argument(
        "--identity-file",
        help="Optional SSH identity file to use for the bootstrap connection",
    )
    parser.add_argument(
        "--ssh-option",
        action="append",
        default=[],
        help="Additional -o SSH option, may be specified multiple times",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print the discovered identity without rewriting the inventory file",
    )
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
    parser.add_argument(
        "--operator-capable",
        action="store_true",
        help="Mark the host as an operator-capable machine in inventory/host-bootstrap.nix",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Commit the inventory updates after enrollment",
    )
    parser.add_argument(
        "--commit-message",
        help="Override the default git commit message used with --commit",
    )
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
    args = parser.parse_args()

    flake_path = Path(args.flake).expanduser().resolve()
    identities_path = flake_path / "inventory" / "private-yggdrasil-identities.nix"
    bootstrap_path = flake_path / "inventory" / "host-bootstrap.nix"
    networks_path = flake_path / "inventory" / "networks.nix"

    if not identities_path.exists():
        raise SystemExit(f"Missing identity inventory file: {identities_path}")
    if not bootstrap_path.exists():
        raise SystemExit(f"Missing bootstrap metadata inventory file: {bootstrap_path}")

    node_names = nix_eval_json(
        networks_path,
        "networks: builtins.attrNames networks.privateYggdrasil.nodes",
    )
    if args.host not in node_names:
        raise SystemExit(
            f"Host '{args.host}' is not present in inventory.networks.privateYggdrasil.nodes."
        )

    identities = nix_eval_json(identities_path)
    bootstrap_metadata = nix_eval_json(bootstrap_path)
    peer_hosts = nix_eval_json(
        networks_path,
        f'networks: (builtins.getAttr {json.dumps(args.host)} networks.privateYggdrasil.nodes).peers or []',
    )

    bootstrap_entry = bootstrap_metadata.get(args.host, {})
    resolved_target = args.target or bootstrap_entry.get("targetHost")
    if resolved_target is None:
        raise SystemExit(
            f"Host '{args.host}' has no bootstrap target configured. Pass --target or set inventory/host-bootstrap.nix."
        )

    args.target = resolved_target
    args.ssh_user = args.ssh_user or bootstrap_entry.get("sshUser", "root")

    ssh_command = build_ssh_command(args)
    try:
        identity_result = run(ssh_command, cwd=flake_path, input_text=REMOTE_SCRIPT)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr)
        raise SystemExit(exc.returncode) from exc

    enrolled_identity = json.loads(identity_result.stdout)

    if args.dry_run:
        print(json.dumps(
            {
                "bootstrap": {
                    "sshUser": args.ssh_user,
                    "targetHost": resolved_target,
                },
                "identity": enrolled_identity,
            },
            indent=2,
            sort_keys=True,
        ))
        return

    identities[args.host] = {
        "address": enrolled_identity["address"],
        "publicKey": enrolled_identity["publicKey"],
    }
    identities_path.write_text(render_identities(node_names, identities))

    updated_bootstrap = dict(bootstrap_entry)
    updated_bootstrap["sshUser"] = args.ssh_user
    updated_bootstrap["targetHost"] = resolved_target
    if args.identity_file is not None:
        updated_bootstrap["identityFile"] = args.identity_file
    elif "identityFile" not in updated_bootstrap:
        updated_bootstrap["identityFile"] = None
    updated_bootstrap["operatorCapable"] = args.operator_capable or bootstrap_entry.get("operatorCapable", False)
    updated_bootstrap["deploymentTransport"] = (
        args.deployment_transport
        or bootstrap_entry.get("deploymentTransport")
        or "bootstrap"
    )
    updated_bootstrap["deploymentTags"] = sorted(
        set(bootstrap_entry.get("deploymentTags", [])) | set(args.deployment_tag)
    )
    bootstrap_metadata[args.host] = updated_bootstrap
    bootstrap_path.write_text(render_bootstrap(node_names, bootstrap_metadata))

    committed = False
    if args.commit:
        commit_message = args.commit_message or f"Enroll Ygg identity for {args.host}"
        committed = git_commit(flake_path, [identities_path, bootstrap_path], commit_message)

    deployed_hosts = []
    if args.deploy_tool is not None:
        deployed_hosts = [args.host]
        if args.deploy_peers:
            deployed_hosts = [args.host, *peer_hosts]
        deploy_hosts(
            flake_path=flake_path,
            hosts=deployed_hosts,
            tool=args.deploy_tool,
        )

    print(f"Updated {identities_path}")
    print(f"Updated {bootstrap_path}")
    print(json.dumps({args.host: identities[args.host]}, indent=2, sort_keys=True))
    print(
        json.dumps(
            {
                args.host: bootstrap_metadata[args.host],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.commit:
        print("Committed inventory updates." if committed else "No staged inventory changes required a commit.")
    if deployed_hosts != []:
        print(f"Deployed hosts with {args.deploy_tool}: {', '.join(deployed_hosts)}")
    print(
        "Next step: rebuild the enrolled host and any peers that should enforce "
        "pinned peer identity or peer-source filtering."
    )


if __name__ == "__main__":
    main()
