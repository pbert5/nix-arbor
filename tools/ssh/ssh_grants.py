"""Read and update Arbor's checkout-local public grants."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
EXTRA = Path('config/access/extra-keys.json')


def display_comment(comment):
    return ''.join(
        char if char.isprintable() or char in '\u200c\u200d'
        else char.encode('unicode_escape').decode('ascii')
        for char in comment
    )


def public_key_info(key):
    parts = key.split(maxsplit=2)
    # Expect one bare public key. OpenSSH's fingerprint command also accepts
    # authorized_keys options and private files, so check the input first.
    if (len(parts) < 2 or not parts[0].startswith(('ssh-', 'ecdsa-', 'sk-'))
            or any(char in key for char in '\x00\n\r')):
        raise ValueError('Expected one bare public SSH key')
    result = subprocess.run(
        ['ssh-keygen', '-l', '-E', 'sha256', '-f', '-'],
        input=' '.join(parts[:2]) + '\n', text=True, capture_output=True,
    )
    if result.returncode:
        raise ValueError('Invalid public SSH key')
    bits, fingerprint, *_, algorithm = result.stdout.split()
    comment = display_comment(parts[2]) if len(parts) == 3 else 'no comment'
    return f'{bits} {fingerprint} {comment} {algorithm}'


def extra_path(root):
    path = root.resolve() / EXTRA
    if path.parent.resolve() != path.parent:
        raise ValueError(f'{EXTRA} must be in the checkout access directory')
    return path


def read_snapshot(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError(f'{EXTRA} must be a regular file')
        return source.read()


def unique_object(pairs):
    data = dict(pairs)
    if len(data) != len(pairs):
        raise ValueError(f'{EXTRA} contains a duplicate host or user')
    return data


def parse_grants(snapshot):
    data = {} if snapshot is None else json.loads(snapshot, object_pairs_hook=unique_object)
    if not isinstance(data, dict):
        raise ValueError(f'{EXTRA} must map hosts to users')
    for host, users in data.items():
        if not host.isprintable() or not isinstance(users, dict):
            raise ValueError(f'{EXTRA} must map hosts to users')
        for user, keys in users.items():
            if (not user.isprintable() or not isinstance(keys, list)
                    or not all(isinstance(key, str) for key in keys)):
                raise ValueError(f'{EXTRA} must map users to lists of public keys')
    return data


@contextmanager
def lock_grants(path):
    # Lock the directory because saving grants replaces the file's inode.
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def save_grants(path, snapshot, data):
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as output:
        temp_path = Path(output.name)
        try:
            json.dump(data, output, indent=2, ensure_ascii=True)
            output.write('\n')
            output.flush()
            temp_path.chmod(0o644)
            if read_snapshot(path) != snapshot:
                raise ValueError(f'{EXTRA} changed. Review the current grants and try again.')
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)
