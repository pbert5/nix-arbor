"""Portable Arbor enrollment file exchange for a joining node."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import subprocess
import sys
import time
from contextlib import closing, contextmanager

ID = r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}"


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def encode(value):
    return base64.urlsafe_b64encode(bytes(value)).decode().rstrip("=")


def decode(value, length):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("invalid base64url value")
    raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if len(raw) != length or encode(raw) != value:
        raise ValueError("invalid encoded key or signature")
    return raw


def crypto():
    try:
        from nacl.signing import SigningKey, VerifyKey
    except ImportError:
        raise ValueError("Enrollment requires PyNaCl. Install it with python -m pip install PyNaCl.") from None
    return SigningKey, VerifyKey


def check_windows_state(directory):
    # SID comparisons are independent of the Windows display language.
    script = """
    $ErrorActionPreference = 'Stop'
    $sid = [System.Security.Principal.SecurityIdentifier]
    $allowed = @([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value,
                 'S-1-5-18', 'S-1-5-32-544')
    $items = @(Get-Item -LiteralPath $env:ARBOR_CHECK_STATE -Force)
    $items += @(Get-ChildItem -LiteralPath $env:ARBOR_CHECK_STATE -Force)
    foreach ($item in $items) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { exit 1 }
        $acl = Get-Acl -LiteralPath $item.FullName
        if ($allowed -notcontains $acl.GetOwner($sid).Value) { exit 1 }
        $raw = [System.Security.AccessControl.RawSecurityDescriptor]::new($acl.Sddl)
        if ($null -eq $raw.DiscretionaryAcl) { exit 1 }
        # Python 3.13 grants OWNER RIGHTS to the owner verified above.
        foreach ($rule in $acl.GetAccessRules($true, $true, $sid)) {
            if ($rule.AccessControlType -eq 'Allow' -and
                $allowed -notcontains $rule.IdentityReference.Value -and
                $rule.IdentityReference.Value -ne 'S-1-3-4') { exit 1 }
        }
    }
    """
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
                            env={**os.environ, "ARBOR_CHECK_STATE": str(directory.resolve())},
                            capture_output=True, timeout=15)
    if result.returncode:
        raise ValueError("private state must be accessible only to this user, SYSTEM and Administrators")


@contextmanager
def database(directory, *, create=False):
    # Windows honors 0700 during directory creation starting with Python 3.13.
    if os.name == "nt" and sys.version_info < (3, 13):
        raise ValueError("Windows enrollment requires Python 3.13 or newer for private directory ACLs")
    private = directory / "enrollment"
    if create:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        private.mkdir(mode=0o700, exist_ok=True)
    info = private.lstat()
    if not stat.S_ISDIR(info.st_mode) or private.is_symlink() or getattr(info, "st_file_attributes", 0) & 1024:
        raise ValueError("invalid enrollment directory")
    if os.name == "nt":
        check_windows_state(private)
    elif (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
        raise ValueError("enrollment directory must be owned by this user with mode 0700")
    file = private / "identity.sqlite"
    if os.name != "nt":
        flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0)
        fd = os.open(file, flags, 0o600)
        try:
            mode = os.fstat(fd)
            if (not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.getuid()
                    or mode.st_mode & 0o077 or mode.st_nlink != 1):
                raise ValueError("enrollment database must be a private, single-link regular file")
        finally:
            os.close(fd)
    elif not create and not file.is_file():
        raise ValueError("no local enrollment request")
    with closing(sqlite3.connect(file)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("CREATE TABLE IF NOT EXISTS identity (id INTEGER PRIMARY KEY, node TEXT, "
                   "authority TEXT, pin TEXT, platform TEXT, seed BLOB, approval TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS requests (digest TEXT PRIMARY KEY, body TEXT)")
        yield db


def request(args):
    SigningKey, _ = crypto()
    if not all(re.fullmatch(ID, s) for s in (args.node, args.authority)) or args.node == args.authority:
        raise ValueError("provide distinct valid node and authority identifiers")
    decode(args.authority_key, 32)
    platform = "windows" if os.name == "nt" else "linux"
    binding = (args.node, args.authority, args.authority_key, platform)
    now = int(time.time())
    with database(args.state_dir, create=True) as db:
        row = db.execute("SELECT node,authority,pin,platform,seed,approval FROM identity WHERE id=1").fetchone()
        if row is None:
            key = SigningKey.generate()
            db.execute("INSERT INTO identity VALUES (1,?,?,?,?,?,NULL)", (*binding, bytes(key)))
        else:
            if row[:4] != binding or row[5] is not None:
                raise ValueError("identity is bound to another request or already approved")
            key = SigningKey(row[4])
        last = db.execute("SELECT body FROM requests ORDER BY rowid DESC LIMIT 1").fetchone()
        body = json.loads(last[0]) if last else None
        if body is None or not body["issuedAt"] <= now < body["expiresAt"]:
            body = dict(kind="arbor-enrollment-request", version=1, generation=1, subject=args.node,
                        nodeId=args.node, requestedParent=args.authority, platform=platform,
                        publicKey=encode(key.verify_key), nonce=encode(secrets.token_bytes(24)),
                        issuedAt=now, expiresAt=now + 900)
            body["signature"] = encode(key.sign(canonical(body)).signature)
            db.execute("INSERT INTO requests VALUES (?,?)", (digest(body), canonical(body).decode()))
    with args.out.open("x", encoding="utf-8") as output:
        output.write(canonical(body).decode() + "\n")
    print(f"Request digest {digest(body)}")


def unique_fields(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate approval field")
        result[name] = value
    return result


def finish(args):
    SigningKey, VerifyKey = crypto()
    from nacl.exceptions import BadSignatureError
    with args.approval.open("rb") as f:
        raw = f.read(65537)
    if len(raw) > 65536:
        raise ValueError("approval exceeds size limit")
    record = json.loads(raw, object_pairs_hook=unique_fields)
    if not isinstance(record, dict) or not isinstance(record.get("payload"), dict):
        raise ValueError("expected a signed node-identity approval")
    signed = dict(record)
    signature = decode(signed.pop("signature", None), 64)
    request_digest = signed["payload"].get("enrollmentRequestDigest")
    if not isinstance(request_digest, str) or not re.fullmatch("[0-9a-f]{64}", request_digest):
        raise ValueError("invalid enrollment request digest")
    with database(args.state_dir) as db:
        identity = db.execute("SELECT node,authority,pin,platform,seed,approval FROM identity WHERE id=1").fetchone()
        pending = db.execute("SELECT body FROM requests WHERE digest=?", (request_digest,)).fetchone()
        if not identity or not pending:
            raise ValueError("no matching local request")
        node, authority, pin, platform, seed, prior = identity
        expected = dict(protocolEpoch=1, wireVersion=1, schemaVersion=1, recordVersion=1,
                        recordId=node, generation=1, predecessor=None, issuer=authority, schema="node-identity",
                        payload=dict(identity=node, publicKey=encode(SigningKey(seed).verify_key),
                                     platform=platform, requestedParent=authority, relationshipScope="dependent",
                                     enrollmentRequestDigest=request_digest, approvedBy=authority, authorityRoot=authority))
        if canonical(signed) != canonical(expected):
            raise ValueError("approval differs from the requested identity or authority")
        try:
            VerifyKey(decode(pin, 32)).verify(canonical(signed), signature)
        except BadSignatureError:
            raise ValueError("invalid authority signature") from None
        approved = canonical(record).decode()
        if prior and prior != approved:
            raise ValueError("different approval already recorded")
        db.execute("UPDATE identity SET approval=? WHERE id=1", (approved,))
    print("Authority approval verified and saved locally.")


def status(args):
    if not (args.state_dir / "enrollment" / "identity.sqlite").exists():
        print("No local enrollment request.")
        return
    with database(args.state_dir) as db:
        row = db.execute("SELECT node,authority,approval IS NOT NULL FROM identity WHERE id=1").fetchone()
    if row:
        print(f"{row[0]} ({row[1]}): " + ("authority approval verified locally" if row[2] else "awaiting authority approval"))
    else:
        print("No local enrollment request.")


def register(parser):
    subs = parser.add_subparsers(dest="enrollment_command", required=True)
    for name, func in (("request", request), ("finish", finish), ("status", status)):
        command = subs.add_parser(name)
        command.add_argument("--state-dir", type=Path, required=True)
        command.set_defaults(handler=run, enrollment_func=func)
        if name == "request":
            for option in ("--node", "--authority", "--authority-key"):
                command.add_argument(option, required=True)
            command.add_argument("--out", type=Path, required=True)
        elif name == "finish":
            command.add_argument("--approval", type=Path, required=True)


def run(args):
    try:
        args.enrollment_func(args)
    except (OSError, ValueError, sqlite3.Error, RecursionError, subprocess.TimeoutExpired) as error:
        print(f"Enrollment failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    register(parser)
    args = parser.parse_args()
    sys.exit(args.handler(args))
