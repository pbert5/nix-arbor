"""Read the Windows provisioning file without passing its contents to a shell."""

import os
from pathlib import Path
import re
import sys
import tempfile


def read_key(path):
    with path.open("rb") as source:
        raw = source.read(1025)
    if len(raw) > 1024:
        raise ValueError
    value = raw.decode("utf-8-sig").removesuffix("\n").removesuffix("\r")
    if not re.fullmatch(r"tskey-auth-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", value):
        raise ValueError
    return value.encode("ascii")


def main(action, mount, staging):
    firmware = Path(mount) / "tailscale-authkey.txt"
    private = Path(staging)
    if not os.path.ismount(mount):
        return 3 if action == "cleanup" else 0
    if action == "cleanup":
        firmware.unlink(missing_ok=True)
        return 0
    try:
        key = read_key(firmware)
    except FileNotFoundError:
        return 0
    except ValueError:
        return 2
    private.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if private.exists() and private.read_bytes() == key:
        return 0
    with tempfile.NamedTemporaryFile(dir=private.parent, delete=False) as target:
        temporary = Path(target.name)
        try:
            target.write(key)
            target.flush()
            os.fsync(target.fileno())
            temporary.replace(private)
        finally:
            temporary.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(*sys.argv[1:]))
    except OSError:
        sys.exit(3)
