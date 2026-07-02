from __future__ import annotations

import os
import shlex
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Any


class ExecutionMode(Enum):
    OPERATE = "operate"
    CHECK = "check"
    PLAN = "plan"


class Privilege(Enum):
    USER = "user"
    ROOT_LOCAL = "root-local"
    ROOT_REMOTE = "root-remote"


class SudoAuthorization(Enum):
    NOT_NEEDED = "already running as root"
    NOPASSWD = "authorized by command-specific NOPASSWD policy"
    CACHED = "authorized by cached sudo credentials"
    PROMPT = "authentication prompt expected"


READ_ONLY_COMMANDS = {
    ("identity", "matrix"),
    ("registry", "status"),
    ("registry", "validate"),
}

PREVIEW_COMMANDS = {
    ("deploy", None),
    ("identity", "generate-missing"),
    ("identity", "rotate"),
    ("install", None),
}


def execution_mode() -> ExecutionMode:
    executable_modes = {
        "clusterchk": ExecutionMode.CHECK.value,
        "clusterplan": ExecutionMode.PLAN.value,
    }
    configured = os.environ.get(
        "CLUSTERCTL_MODE",
        executable_modes.get(Path(sys.argv[0]).name, ExecutionMode.OPERATE.value),
    )
    try:
        return ExecutionMode(configured)
    except ValueError as error:
        choices = ", ".join(mode.value for mode in ExecutionMode)
        raise ValueError(
            f"invalid CLUSTERCTL_MODE {configured!r}; expected one of: {choices}"
        ) from error


def command_identity(args: Any) -> tuple[str, str | None]:
    command = args.command
    return command, getattr(args, f"{command.replace('-', '_')}_command", None)


def prepare_invocation(args: Any, mode: ExecutionMode) -> None:
    identity = command_identity(args)
    if mode is ExecutionMode.OPERATE:
        return
    if identity in READ_ONLY_COMMANDS:
        if mode is ExecutionMode.CHECK and identity == ("identity", "matrix"):
            args.fetch = False
            args.status_ack = False
        return
    if mode is ExecutionMode.CHECK:
        raise ValueError(
            f"clusterchk only permits read-only commands; rejected {' '.join(filter(None, identity))}"
        )
    if identity not in PREVIEW_COMMANDS:
        raise ValueError(
            f"clusterplan has no safe preview for {' '.join(filter(None, identity))}"
        )
    args.dry_run = True
    if hasattr(args, "publish"):
        args.publish = False
    if hasattr(args, "publish_identities"):
        args.publish_identities = False


def privileged_command(
    command: list[str],
    privilege: Privilege,
    *,
    preserve_env: tuple[str, ...] = (),
) -> list[str]:
    if privilege is Privilege.USER or os.geteuid() == 0:
        return command
    if privilege is Privilege.ROOT_REMOTE:
        raise ValueError(
            "remote-root commands must express sudo inside the SSH command"
        )
    prefix = ["sudo"]
    if preserve_env:
        prefix.append(f"--preserve-env={','.join(preserve_env)}")
    return [*prefix, "--", *command]


def sudo_authorization_status(
    command: list[str],
    *,
    runner: Any = subprocess.run,
) -> SudoAuthorization:
    if os.geteuid() == 0:
        return SudoAuthorization.NOT_NEEDED
    listed = runner(
        ["sudo", "-n", "-l", "--", *command],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if listed.returncode == 0 and "NOPASSWD:" in (getattr(listed, "stdout", "") or ""):
        return SudoAuthorization.NOPASSWD
    validated = runner(
        ["sudo", "-n", "-v"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if validated.returncode == 0:
        return SudoAuthorization.CACHED
    return SudoAuthorization.PROMPT


def run(
    command: list[str],
    *,
    privilege: Privilege = Privilege.USER,
    check: bool = False,
    runner: Any = subprocess.run,
    authorization_runner: Any = subprocess.run,
    **kwargs: Any,
) -> subprocess.CompletedProcess:
    prepared = privileged_command(command, privilege)
    if privilege is not Privilege.USER:
        print(f"PRIVILEGED ({privilege.value}): {shlex.join(command)}", flush=True)
        status = sudo_authorization_status(command, runner=authorization_runner)
        print(f"SUDO AUTHORIZATION: {status.value}", flush=True)
    return runner(prepared, check=check, **kwargs)
