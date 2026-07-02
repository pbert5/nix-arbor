import shlex
import subprocess


class InstallError(RuntimeError):
    pass


def resolve_plan(inventory: dict, host: str) -> dict:
    hosts = inventory.get("hosts") or {}
    bootstrap_hosts = inventory.get("hostBootstrap") or {}
    if host not in hosts:
        raise InstallError(f"unknown inventory host: {host}")
    if host not in bootstrap_hosts:
        raise InstallError(f"{host} has no host-bootstrap entry")

    host_install = ((hosts[host].get("org") or {}).get("install") or {})
    install = bootstrap_hosts[host].get("install") or {}
    if install.get("enable") is not True or host_install.get("enable") is not True:
        raise InstallError(
            f"{host} is not explicitly enabled in both inventory files"
        )

    installation_id = install.get("installationId")
    if not installation_id or installation_id != host_install.get("installationId"):
        raise InstallError(f"{host} has mismatched installationId safety latches")

    disks = ((install.get("disko") or {}).get("devices") or {}).get("disk") or {}
    configured_devices = [
        disk.get("device")
        for disk in disks.values()
        if isinstance(disk, dict) and disk.get("device")
    ]
    if len(configured_devices) != 1:
        raise InstallError(f"{host} must configure exactly one install disk")

    required = [
        "targetHost",
        "sshUser",
        "expectedLiveHostName",
        "expectedLiveMarker",
        "expectedHardware",
        "expectedDiskSize",
    ]
    missing = [name for name in required if not install.get(name)]
    if missing:
        raise InstallError(
            f"{host} install inventory is missing: {', '.join(missing)}"
        )

    return {
        **install,
        "host": host,
        "device": configured_devices[0],
    }


def ssh_command(plan: dict, remote_command: str) -> list[str]:
    command = ["ssh", "-p", str(plan.get("sshPort", 22))]
    identity_file = plan.get("identityFile")
    if identity_file:
        command.extend(["-i", identity_file, "-o", "IdentitiesOnly=yes"])
    command.extend(
        [
            f"{plan['sshUser']}@{plan['targetHost']}",
            f"sh -c {shlex.quote(remote_command)}",
        ]
    )
    return command


def probe_script(device: str) -> str:
    quoted_device = shlex.quote(device)
    return f"""
set -eu
value() {{
  printf '%s=' "$1"
  cat "$2" 2>/dev/null || true
  printf '\\n'
}}
printf 'hostname='; hostname
printf 'os_id='
(
  . /etc/os-release 2>/dev/null
  printf '%s' "$ID"
) || true
printf '\\n'
printf 'root_source='; findmnt -n -o SOURCE / 2>/dev/null || true
printf 'root_fstype='; findmnt -n -o FSTYPE / 2>/dev/null || true
value live_marker /etc/clusterctl-install-target
value sys_vendor /sys/class/dmi/id/sys_vendor
value product_name /sys/class/dmi/id/product_name
if [ -b {quoted_device} ]; then
  printf 'disk_exists=true\\n'
  printf 'disk_size='; lsblk -bdno SIZE {quoted_device}
  printf 'disk_model='; lsblk -dno MODEL {quoted_device} | sed 's/[[:space:]]*$//'
  if lsblk -nrpo MOUNTPOINT {quoted_device} | grep -q '[^[:space:]]'; then
    printf 'disk_mounted=true\\n'
  else
    printf 'disk_mounted=false\\n'
  fi
else
  printf 'disk_exists=false\\n'
  printf 'disk_size=\\n'
  printf 'disk_model=\\n'
  printf 'disk_mounted=false\\n'
fi
""".strip()


def parse_probe(output: str) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in output.splitlines()
        if "=" in line
    )


def probe(plan: dict) -> dict[str, str]:
    completed = subprocess.run(
        ssh_command(plan, probe_script(plan["device"])),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return parse_probe(completed.stdout)


def validate_probe(plan: dict, result: dict[str, str]) -> None:
    expected_hardware = plan["expectedHardware"]
    checks = {
        "hostname": plan["expectedLiveHostName"],
        "live_marker": plan["expectedLiveMarker"],
        "sys_vendor": expected_hardware.get("sysVendor"),
        "product_name": expected_hardware.get("productName"),
    }
    for field, expected in checks.items():
        if expected and result.get(field) != expected:
            raise InstallError(
                f"remote {field} is {result.get(field)!r}, expected {expected!r}"
            )

    if result.get("disk_exists") != "true":
        raise InstallError(f"configured install disk {plan['device']} does not exist")
    if result.get("disk_mounted") != "false":
        raise InstallError(f"configured install disk {plan['device']} is mounted")

    try:
        disk_size = int(result.get("disk_size", ""))
    except ValueError as error:
        raise InstallError("could not read configured install disk size") from error
    expected_size = plan["expectedDiskSize"]
    if not (
        expected_size["minimumBytes"]
        <= disk_size
        <= expected_size["maximumBytes"]
    ):
        raise InstallError(
            f"configured install disk is {disk_size} bytes, outside expected "
            f"range {expected_size['minimumBytes']}..{expected_size['maximumBytes']}"
        )

    if result.get("os_id") == "nixos":
        ephemeral_filesystems = {"overlay", "squashfs", "tmpfs"}
        if result.get("root_fstype") not in ephemeral_filesystems:
            raise InstallError(
                "refusing to overwrite a machine running installed NixOS "
                f"(root {result.get('root_source')!r}, "
                f"type {result.get('root_fstype')!r})"
            )


def command(plan: dict, flake: str) -> list[str]:
    # Stay in the verified repo installer boot so the checked /dev mapping
    # cannot change under a nixos-anywhere kexec.
    result = [
        "nixos-anywhere",
        "--flake",
        f"{flake}#{plan['host']}",
        "--target-host",
        f"{plan['sshUser']}@{plan['targetHost']}",
        "--phases",
        "disko,install,reboot",
    ]
    identity_file = plan.get("identityFile")
    if identity_file:
        result.extend(["-i", identity_file])
    if plan.get("sshPort", 22) != 22:
        result.extend(["--ssh-port", str(plan["sshPort"])])
    return result
