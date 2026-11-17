#!/usr/bin/env python3
"""Portable Arbor guest client for Linux and Windows."""

import argparse
import contextlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import uuid

import arbor_enrollment

WINDOWS = os.name == "nt"
INTERFACE = "arbor-ygg"
OVERLAY = ipaddress.IPv6Network("200::/7")
KEY = re.compile(r"[0-9a-fA-F]{128}")
PEER = re.compile(r"(tls|tcp|quic)://(\[[0-9A-Fa-f:]+\]|[a-zA-Z0-9.-]+):([0-9]+)\?key=([0-9a-fA-F]{64})")


def binary(name):
    path = shutil.which(name)
    if not path and WINDOWS and name == "yggdrasil":
        candidate = Path(os.environ["ProgramFiles"]) / "Yggdrasil" / "yggdrasil.exe"
        if candidate.is_file():
            path = str(candidate)
    if not path:
        raise ValueError(f"Install {name} and put it on PATH (see README.md).")
    return path


def ygg():
    exe = binary("yggdrasil")
    output = subprocess.check_output([exe, "-version"], text=True)
    version = re.search(r"Build version:\s*v?0\.5\.(\d+)\b", output)
    if not version or int(version[1]) < (15 if WINDOWS else 14):
        raise ValueError("Requires Yggdrasil 0.5.x (Linux >=0.5.14, Windows >=0.5.15).")
    return exe


def valid_peer(uri):
    match = PEER.fullmatch(uri)
    if not match or not 1 <= int(match[3]) <= 65535:
        raise ValueError("Expected tls/tcp/quic://host:port?key=<64 hexadecimal digits>.")
    if match[2].startswith("["):
        ipaddress.IPv6Address(match[2][1:-1])
    return uri


def overlay(address):
    ip = ipaddress.IPv6Address(address)
    if ip not in OVERLAY or ip.scope_id:
        raise ValueError("Expected an IPv6 address in 200::/7.")
    return str(ip)


def private_dir(path):
    if WINDOWS and sys.version_info < (3, 13):
        raise ValueError("Windows requires Python 3.13+ for private directory ACL support.")
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink() or getattr(info, "st_file_attributes", 0) & 1024:
        raise ValueError("Expected a private state directory.")
    if WINDOWS:
        arbor_enrollment.check_windows_state(path)
    elif (info.st_uid != os.geteuid() or info.st_mode & 0o077):
        raise ValueError("State must be owned by the running account and mode 0700.")


def identity(state, exe):
    def field(key, flag):
        return subprocess.check_output(
            [exe, "-useconf", flag], input=json.dumps({"PrivateKey": key}), text=True
        ).strip()
    return {
        "privatePublicKey": field(state["private"], "-publickey"),
        "privateAddress": overlay(field(state["private"], "-address")),
        "sidecarPublicKey": field(state["sidecar"], "-publickey"),
    }


def initialize(args):
    exe = ygg()
    peers = [valid_peer(uri) for uri in args.peer]
    keys = [json.loads(subprocess.check_output([exe, "-genconf", "-json"]))["PrivateKey"]
            for _ in range(2)]
    state = dict(private=keys[0], sidecar=keys[1], peers=peers, port=args.port)
    validate(state)
    public = identity(state, exe)
    # Exclusively create the profile. A failed or repeated init can never rotate keys.
    if WINDOWS and sys.version_info < (3, 13):
        raise ValueError("Windows requires Python 3.13+.")
    args.state_dir.mkdir(mode=0o700)
    private_dir(args.state_dir)
    fd = os.open(args.state_dir / "identity.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps(public, indent=2))


def validate(state):
    for role in ("private", "sidecar"):
        if not KEY.fullmatch(state[role]):
            raise ValueError("Invalid saved Yggdrasil key.")
    if state["private"][-64:] == state["sidecar"][-64:]:
        raise ValueError("Private and sidecar identities must differ.")
    if not 1 <= state["port"] <= 65535 or not state["peers"]:
        raise ValueError("Expected a bridge port and at least one pinned upstream peer.")
    for uri in state["peers"]:
        valid_peer(uri)


def read_state(args):
    private_dir(args.state_dir)
    path = args.state_dir / "identity.json"
    if not WINDOWS:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError("Expected a private, owned, single-link identity file.")
    state = json.loads(path.read_bytes())
    validate(state)
    return state


def configs(state, public, peers):
    local = f"tls://127.0.0.1:{state['port']}"
    common = dict(AdminListen="none", InterfacePeers={}, MulticastInterfaces=[], NodeInfoPrivacy=True)
    return [
        dict(common, PrivateKey=state["sidecar"], IfName="none", Peers=peers,
             Listen=[local], AllowedPublicKeys=[public["privatePublicKey"]]),
        dict(common, PrivateKey=state["private"], IfName=INTERFACE,
             Peers=[local + "?key=" + public["sidecarPublicKey"]], Listen=[],
             AllowedPublicKeys=[public["sidecarPublicKey"]]),
    ]


def powershell(script):
    return subprocess.check_output(
        [binary("powershell.exe"), "-NoProfile", "-NonInteractive", "-Command",
         "$ErrorActionPreference='Stop'; " + script], text=True
    ).strip()


def interface_addresses():
    if WINDOWS:
        result = powershell(
            "Get-NetIPAddress -AddressFamily IPv6 | "
            f"Where-Object InterfaceAlias -eq '{INTERFACE}' | Select-Object -ExpandProperty IPAddress")
        return result.splitlines()
    interfaces = json.loads(subprocess.check_output([binary("ip"), "-j", "-6", "addr"]))
    return [entry["local"] for iface in interfaces if iface["ifname"] == INTERFACE
            for entry in iface["addr_info"]]


@contextlib.contextmanager
def firewall(name):
    # Install before opening either peer. Keep unrelated host policies intact.
    if WINDOWS:
        powershell(
            "if (Get-NetFirewallProfile -PolicyStore ActiveStore | Where-Object { $_.Enabled -ne 'True' -or $_.AllowLocalFirewallRules -eq 'False' }) "
            "{ throw 'All firewall profiles must enforce local rules' }; "
            f"New-NetFirewallRule -Name '{name}' -DisplayName '{name}' -PolicyStore PersistentStore "
            "-Direction Inbound -Action Block -Profile Any -RemoteAddress '200::/7' | Out-Null")
        try:
            yield
        finally:
            powershell(f"Remove-NetFirewallRule -PolicyStore PersistentStore -Name '{name}'")
    else:
        nft = binary("nft")
        rules = (f"create table inet {name}\n"
                 f"add chain inet {name} input {{ type filter hook input priority -5; policy accept; }}\n"
                 f'add rule inet {name} input iifname "{INTERFACE}" ct state established,related accept\n'
                 f'add rule inet {name} input iifname "{INTERFACE}" drop\n'
                 f"add chain inet {name} forward {{ type filter hook forward priority -5; policy accept; }}\n"
                 f'add rule inet {name} forward iifname "{INTERFACE}" drop\n'
                 f'add rule inet {name} forward oifname "{INTERFACE}" drop\n')
        subprocess.run([nft, "-f", "-"], input=rules, text=True, check=True)
        try:
            yield
        finally:
            subprocess.run([nft, "delete", "table", "inet", name], check=True)


@contextlib.contextmanager
def profile_lock(path):
    with (path / "running.lock").open("a+b") as f:
        f.seek(0)
        try:
            if WINDOWS:
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("This profile already has a running supervisor.") from exc
        yield


@contextlib.contextmanager
def daemon(exe, config):
    proc = subprocess.Popen([exe, "-useconf"], stdin=subprocess.PIPE)
    try:
        with proc.stdin as pipe:
            pipe.write(json.dumps(config).encode())
        yield proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def run(args):
    state = read_state(args)
    exe = ygg()
    public = identity(state, exe)
    stop = args.state_dir / "stop"
    peers = [valid_peer(p) for p in args.peer] if args.peer else state["peers"]
    with profile_lock(args.state_dir), contextlib.ExitStack() as stack:
        stop.unlink(missing_ok=True)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if WINDOWS:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            probe.bind(("127.0.0.1", state["port"]))
        if WINDOWS:
            powershell(f"if (Get-NetAdapter -IncludeHidden | Where-Object {{ $_.Name -eq '{INTERFACE}' -or "
                       "($_.InterfaceGuid -as [Guid]) -eq [Guid]'8f59971a-7872-4aa6-b2eb-061fc4e9d0a7' }) "
                       "{ throw 'A conflicting Wintun adapter already exists' }; "
                       "if (Get-Process -Name yggdrasil -ErrorAction SilentlyContinue) "
                       "{ throw 'An existing Yggdrasil process is using this host' }; "
                       "if (Get-NetRoute -AddressFamily IPv6 | Where-Object DestinationPrefix -eq '200::/7') "
                       "{ throw 'An existing Yggdrasil route is present' }; "
                       "if (Get-NetIPInterface -AddressFamily IPv6 | Where-Object Forwarding -eq Enabled) "
                       "{ throw 'An outbound client requires IPv6 forwarding disabled' }")
        else:
            ip = binary("ip")
            if json.loads(subprocess.check_output([ip, "-j", "-6", "route", "show", "table", "all", "exact", "200::/7"])):
                raise ValueError("Another Yggdrasil route exists. Release it before running this client.")
            if any(link["ifname"] == INTERFACE for link in json.loads(subprocess.check_output([ip, "-j", "link"]))):
                raise ValueError(f"Interface {INTERFACE} already exists.")
        journal = args.state_dir / "session.json"
        if journal.exists():
            raise ValueError("An interrupted session needs inspection. See README.md under Crash recovery.")
        session = {"supervisorPid": os.getpid(), "firewall": "arbor_ygg_" + uuid.uuid4().hex,
                   "daemonPids": [], "executable": exe}
        journal.write_text(json.dumps(session), encoding="utf-8")
        # Run resource cleanup separately from exceptions in the supervisor.
        # Leave recovery information only when closing an owned resource failed.
        resources = contextlib.ExitStack()
        def cleanup():
            resources.close()
            journal.unlink(missing_ok=True)
        stack.callback(cleanup)
        resources.enter_context(firewall(session["firewall"]))
        if WINDOWS:
            name = session["firewall"]
            powershell(f"$rule = Get-NetFirewallRule -PolicyStore ActiveStore -Name '{name}'; "
                       "if ($rule.Enabled -ne 'True' -or $rule.Action -ne 'Block' -or "
                       "$rule.PrimaryStatus -ne 'OK') { throw 'Inbound block rule is inactive' }")
        daemons = []
        for conf in configs(state, public, peers):
            proc = resources.enter_context(daemon(exe, conf))
            daemons.append(proc)
            session["daemonPids"].append(proc.pid)
            update = journal.with_suffix(".tmp")
            update.write_text(json.dumps(session), encoding="utf-8")
            update.replace(journal)
        ready = False
        deadline = time.monotonic() + 30
        while not stop.exists():
            if any(p.poll() is not None for p in daemons):
                raise ValueError("A Yggdrasil daemon exited. See its output above.")
            if not ready:
                if public["privateAddress"] in interface_addresses():
                    print("Private interface ready. Check remote connectivity with 'check'. Ctrl+C to stop.", flush=True)
                    ready = True
                elif time.monotonic() >= deadline:
                    raise ValueError("Timed out waiting for the private interface.")
            time.sleep(.4)


def main():
    default = (Path(os.environ["LOCALAPPDATA"]) / "ArborConnect" if WINDOWS
               else Path("/var/lib/arbor-connect"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=default, help=f"private profile (default {default})")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init", help="create two identities and remember operator-provided upstreams")
    init.add_argument("--peer", action="append", required=True, help="pinned upstream sidecar URI (repeatable)")
    init.add_argument("--port", type=int, default=14743, help="local loopback bridge port")
    sub.add_parser("identity", help="print only public handoff values")
    up = sub.add_parser("up", help="start and supervise both daemons until Ctrl+C or down")
    up.add_argument("--peer", action="append", help="temporarily replace the saved upstream list")
    sub.add_parser("down", help="ask this profile's supervisor to shut down")
    sub.add_parser("status", help="check the private identity's interface address")
    for cmd, desc in [("check", "test a remote overlay TCP service"), ("ssh", "open an OpenSSH session")]:
        p = sub.add_parser(cmd, help=desc)
        p.add_argument("address", type=overlay)
        p.add_argument("--port", type=int, default=22)
        if cmd == "ssh":
            p.add_argument("--user", required=True)
    enrollment = sub.add_parser("enrollment", help="Arbor Registry operator pairing")
    arbor_enrollment.register(enrollment)
    args = parser.parse_args()
    if args.cmd == "enrollment":
        return args.handler(args)
    if args.cmd == "init":
        initialize(args)
    elif args.cmd == "up":
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        run(args)
    elif args.cmd == "down":
        private_dir(args.state_dir)
        (args.state_dir / "stop").touch()
        print("Shutdown requested. The foreground 'up' command exits after cleanup.")
    elif args.cmd in ("identity", "status"):
        public = identity(read_state(args), ygg())
        if args.cmd == "status":
            public["interfaceReady"] = public["privateAddress"] in interface_addresses()
        print(json.dumps(public, indent=2))
        return 1 if public.get("interfaceReady") is False else 0
    else:
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be 1–65535.")
        if args.cmd == "check":
            with socket.create_connection((args.address, args.port), timeout=5):
                print(f"Connected to [{args.address}]:{args.port}")
        else:
            if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.-]*", args.user):
                raise ValueError("Invalid SSH username.")
            return subprocess.call([binary("ssh"), "-6", "-p", str(args.port), "-l", args.user, args.address])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        sys.exit(str(error))
