"""Read-only local artifact and explicitly selected Pi inspection."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

STATES = {'missing-key', 'waiting', 'retrying', 'pending-approval', 'enrolled', 'indeterminate'}


def safe_state(value):
    value = value.strip()
    return value if value in STATES else 'indeterminate'


def valid_remote(value):
    return bool(re.fullmatch(r'(?:[A-Za-z0-9_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9.-]*', value))


def verify_artifact(image, manifest):
    if (manifest.get('schema_version') != 1 or type(manifest.get('result_size')) is not int
            or type(manifest.get('personalized')) is not bool):
        raise ValueError('unsupported artifact manifest')
    digest = hashlib.sha256()
    size = 0
    with image.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    hexdigest = digest.hexdigest()
    if size != manifest['result_size'] or hexdigest != manifest.get('result_sha256'):
        raise ValueError('artifact size or digest does not match manifest')
    return size, hexdigest


def remote(target, command):
    return subprocess.run(['ssh', '--', target, command], capture_output=True, text=True, timeout=30, check=False)


def main():
    parser = argparse.ArgumentParser(description='Inspect a local image manifest or a selected Pi over SSH.')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--image', type=Path, help='image whose adjacent .json manifest is checked')
    group.add_argument('--remote', metavar='[USER@]HOST', help='explicit SSH destination')
    args = parser.parse_args()
    if args.image:
        try:
            manifest = json.loads(Path(str(args.image) + '.json').read_text())
            size, digest = verify_artifact(args.image, manifest)
            print(f'Image: {args.image}\nBytes: {size}\nSHA-256: {digest}')
            print('Personalized:', 'yes' if manifest.get('personalized') is True else 'no')
        except (OSError, ValueError, json.JSONDecodeError):
            print('Cannot verify artifact and adjacent manifest.', file=sys.stderr)
            return 1
        return 0
    if not valid_remote(args.remote):
        parser.error('invalid SSH destination')
    try:
        status = remote(args.remote, 'cat /run/raspberry-evolver/bootstrap.status')
        service = remote(args.remote, 'systemctl is-active raspberry-evolver-bootstrap.service')
        tailnet = remote(args.remote, 'tailscale status --json')
        space = remote(args.remote, 'df -Pk /')
    except (OSError, subprocess.TimeoutExpired):
        print('SSH inspection failed; check SSH access and try again.', file=sys.stderr)
        return 1
    print('Bootstrap:', safe_state(status.stdout) if status.returncode == 0 else 'not yet run or unavailable')
    service_state = service.stdout.strip()
    print('Service:', service_state if service_state in {'active', 'inactive', 'failed', 'activating', 'deactivating'} else 'unavailable')
    try:
        name = json.loads(tailnet.stdout).get('CurrentTailnet', {}).get('Name')
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,253}', name):
            name = 'unavailable'
    except (ValueError, AttributeError):
        name = 'unavailable'
    print('Observed tailnet:', name)
    rows = space.stdout.splitlines()
    columns = rows[-1].split() if len(rows) >= 2 else []
    if space.returncode == 0 and len(columns) >= 6 and all(c.isdigit() for c in columns[1:4]):
        print(f'Root KiB: total={columns[1]} used={columns[2]} available={columns[3]}')
    else:
        print('Root space: unavailable')
    return 0 if status.returncode == 0 and space.returncode == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
