#!/usr/bin/env python3
"""Inspect or explicitly write an image to a whole, unused block device."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import pathlib
import stat
import struct
import subprocess
import sys

import artifact

SYS = pathlib.Path('/sys/class/block')
MIN_CARD_BYTES = 29_500_000_000  # Allow normal 32 GB cards with manufacturer rounding.
CHUNK = 1024 * 1024


class SafetyError(Exception):
    pass


def digest(file, size):
    result = hashlib.sha256()
    while size:
        data = file.read(min(size, CHUNK))
        if not data:
            raise SafetyError('short read during digest')
        result.update(data)
        size -= len(data)
    return result.hexdigest()


def copy_and_verify(source, target, size, expected):
    remaining = size
    while remaining:
        data = source.read(min(remaining, CHUNK))
        if not data:
            raise SafetyError('short image read; media may be partially written')
        view = memoryview(data)
        while view:
            written = target.write(view)
            if not written:
                raise SafetyError('short device write; media may be partially written')
            view = view[written:]
        remaining -= len(data)
    target.flush()
    os.fsync(target.fileno())
    target.seek(0)
    if digest(target, size) != expected:
        raise SafetyError('readback verification failed; media may be partially written')


def validate_graph(graph, selected, mounted, swaps, source_dev, image_size):
    if selected not in graph or graph[selected]['type'] != 'disk':
        raise SafetyError('select a resolved whole disk, not a partition')
    disk = graph[selected]
    if not disk['identity']:
        raise SafetyError('device has no stable serial or WWID')
    if disk['size'] < MIN_CARD_BYTES or disk['size'] < image_size:
        raise SafetyError('device is too small: use a 32 GB or larger card that fits the image')
    if source_dev not in graph or graph[source_dev]['type'] == 'virtual':
        raise SafetyError('cannot resolve a supported image filesystem backing device; move the image to a directly backed filesystem')
    seen = set()
    def visit(dev):
        if dev in seen or dev not in graph:
            raise SafetyError('ambiguous or incomplete block graph')
        seen.add(dev)
        node = graph[dev]
        if node['ro'] or node['holders'] or dev in mounted or dev in swaps or dev == source_dev:
            raise SafetyError('device or partition is read-only, mounted, swap, backing the image, or has holders')
        for child in node['children']:
            visit(child)
    visit(selected)
    return seen


def validate_manifest(image, size, sha):
    try:
        with open(str(image) + '.json', encoding='utf-8') as manifest:
            data = json.load(manifest)
        artifact.validate(data)
        if data['result_size'] != size or data['result_sha256'] != sha:
            raise SafetyError('image manifest size or SHA-256 does not match')
    except (OSError, ValueError) as error:
        raise SafetyError('cannot read a valid adjacent image manifest') from error


def same_device(before, after):
    if before != after:
        raise SafetyError('device identity or safety state changed; refusing to write')


def read(path):
    return path.read_text().strip()


def zpool_leaves(output):
    if output.strip() == 'no pools available':
        return []
    sections = output.split('config:')[1:]
    if not sections or len(sections) != output.count('  pool:'):
        raise SafetyError('cannot parse ZFS pool topology')
    leaves = []
    for section in sections:
        if 'errors:' not in section:
            raise SafetyError('incomplete ZFS pool topology')
        config = section.split('errors:', 1)[0].splitlines()
        header = next((i for i, line in enumerate(config)
                       if line.split()[:2] == ['NAME', 'STATE']), None)
        if header is None:
            raise SafetyError('missing ZFS topology header')
        rows = []
        for line in config[header + 1:]:
            fields = line.split()
            if not fields or fields[0] in ('logs', 'cache', 'spares', 'special', 'dedup'):
                continue
            if len(fields) < 2 or fields[1] not in ('ONLINE', 'DEGRADED', 'FAULTED', 'OFFLINE', 'UNAVAIL', 'REMOVED', 'AVAIL', 'INUSE'):
                raise SafetyError('unrecognized ZFS topology row')
            rows.append((len(line) - len(line.lstrip()), fields[0]))
        if len(rows) < 2:
            raise SafetyError('empty ZFS pool topology')
        for index, (indent, name) in enumerate(rows):
            if index + 1 < len(rows) and rows[index + 1][0] > indent:
                continue
            if not name.startswith('/dev/'):
                raise SafetyError('ZFS pool has an unresolved or non-device leaf')
            leaves.append(name)
    return leaves


def zfs_devices(graph):
    if not pathlib.Path('/sys/module/zfs').exists():
        return set()
    result = subprocess.run(['zpool', 'status', '-LP'], check=True, capture_output=True,
                            text=True, env={**os.environ, 'LC_ALL': 'C'})
    devices = set()
    for path in zpool_leaves(result.stdout):
        info = os.stat(path)
        if not stat.S_ISBLK(info.st_mode):
            raise SafetyError('ZFS pool leaf is not a block device')
        dev = f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'
        if dev not in graph:
            raise SafetyError('cannot resolve a ZFS pool leaf in the block graph')
        devices.add(dev)
    return devices


def mounted_devices(path=pathlib.Path('/proc/self/mountinfo')):
    """Inspect mounts visible to this process; do not claim all namespaces."""
    mounted = set()
    lines = path.read_text().splitlines()
    if not lines:
        raise SafetyError('cannot read visible mounts')
    for line in lines:
        fields = line.split()
        if len(fields) < 10 or '-' not in fields:
            raise SafetyError('cannot parse mount information')
        mounted.add(fields[2])
    return mounted


def snapshot():
    # Btrfs can own multiple devices without sysfs holders.
    if pathlib.Path('/sys/module/btrfs').exists():
        raise SafetyError('Btrfs is loaded; block ancestry cannot be proven safe')
    graph = {}
    nodes = []
    for entry in SYS.iterdir():
        real = entry.resolve(strict=True)
        dev = read(entry / 'dev')
        kind = 'part' if (entry / 'partition').exists() else 'disk'
        if str(real).startswith('/sys/devices/virtual/') and kind == 'disk':
            kind = 'virtual'
        identity = ''
        for path in (entry / 'device/wwid', entry / 'wwid', entry / 'device/serial'):
            try:
                identity = read(path)
            except OSError:
                continue
            if identity:
                break
        node = {'type': kind, 'size': int(read(entry / 'size')) * 512,
                'ro': read(entry / 'ro') != '0', 'children': [],
                'holders': sorted(p.name for p in (entry / 'holders').iterdir()),
                'identity': identity, 'name': entry.name,
                'model': read(entry / 'device/model') if (entry / 'device/model').exists() else ''}
        if dev in graph:
            raise SafetyError('duplicate block device identity')
        graph[dev] = node
        nodes.append((dev, real))
    for child, child_path in nodes:
        if graph[child]['type'] == 'part':
            parents = [dev for dev, path in nodes if path == child_path.parent]
            if len(parents) != 1:
                raise SafetyError('cannot resolve partition ancestry')
            graph[parents[0]]['children'].append(child)
    for node in graph.values():
        node['children'].sort()
    mounted = mounted_devices()
    swaps = set()
    for line in pathlib.Path('/proc/swaps').read_text().splitlines()[1:]:
        fields = line.split()
        if not fields:
            raise SafetyError('cannot parse swap information')
        info = os.stat(fields[0].replace('\\040', ' '))
        dev = info.st_rdev if stat.S_ISBLK(info.st_mode) else info.st_dev
        swaps.add(f'{os.major(dev)}:{os.minor(dev)}')
    mounted.update(zfs_devices(graph))
    return graph, mounted, swaps


@contextlib.contextmanager
def instance_lock(selected):
    """Serialize cooperating tool instances on this host."""
    path = '/run/lock/raspberry-evolver-' + selected.replace(':', '-') + '.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1:
            raise SafetyError('unsafe local lock; inspect /run/lock before retrying')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SafetyError('another flash operation holds the local device lock') from None
        yield
    finally:
        os.close(fd)


def elevate(args):
    result = subprocess.run(['sudo', '--', sys.executable, str(pathlib.Path(__file__).resolve()),
                             '--write', args.image, args.device], check=False)
    if result.returncode:
        raise SafetyError('privileged inspection or write did not complete; no retry was attempted')


def main():
    parser = argparse.ArgumentParser(description='Inspect a target; --write and typed confirmation are required to flash it. No automatic sudo or unmounting.')
    parser.add_argument('image', nargs='?', help='uncompressed image file')
    parser.add_argument('device', nargs='?', help='explicit whole block device')
    parser.add_argument('--write', action='store_true', help='enable writing after typed confirmation')
    args = parser.parse_args()
    if not args.image and not args.device and not args.write:
        parser.print_help()
        print('\nBlock device inventory:', flush=True)
        subprocess.run(['lsblk', '-b', '-o', 'NAME,TYPE,SIZE,RO,MODEL,SERIAL,MOUNTPOINTS'], check=True)
        return
    if not args.image or not args.device:
        parser.error('provide both IMAGE and DEVICE')
    path = os.path.realpath(args.device, strict=True)
    info = os.stat(path)
    if not stat.S_ISBLK(info.st_mode):
        raise SafetyError('target is not a block device')
    selected = f'{os.major(info.st_rdev)}:{os.minor(info.st_rdev)}'
    with open(args.image, 'rb') as source:
        image_info = os.fstat(source.fileno())
        if not stat.S_ISREG(image_info.st_mode) or image_info.st_size == 0:
            raise SafetyError('image must be a nonempty regular file')
        source_dev = f'{os.major(image_info.st_dev)}:{os.minor(image_info.st_dev)}'
        sha = digest(source, image_info.st_size)
        validate_manifest(args.image, image_info.st_size, sha)
        graph, mounted, swaps = snapshot()
        members = validate_graph(graph, selected, mounted, swaps, source_dev, image_info.st_size)
        disk = graph[selected]
        print(f'Image: {os.path.realpath(args.image)}\nBytes: {image_info.st_size}\nSHA-256: {sha}')
        print(f'Device: {path} ({selected})\nModel: {disk["model"] or "unknown"}\nStable identity: {disk["identity"]}\nCapacity: {disk["size"]} bytes')
        print('Partitions: ' + (', '.join(graph[d]['name'] for d in sorted(members - {selected})) or 'none'))
        print('Visible mountpoints on target or partitions: none')
        print('Inspection scope: visible mounts, swap, source filesystem, holders and supported block topology.')
        print('Assumes a controlled host with cooperating administrators and no concurrent raw writer.')
        print(f'Action: overwrite the first {image_info.st_size} bytes, sync and verify that byte range.')
        if not args.write:
            print('Dry run only. Add --write for an interactive confirmation.')
            return
        if os.geteuid() != 0:
            print('Privileged read-only inspection is required before final consent; sudo will be requested.', flush=True)
            elevate(args)
            return
        phrase = f'{path} {disk["identity"]} {disk["size"]}'
        if input(f'Type exactly "{phrase}" to write: ') != phrase:
            raise SafetyError('confirmation did not match; no write performed')
        current_graph, current_mounts, current_swaps = snapshot()
        validate_graph(current_graph, selected, current_mounts, current_swaps, source_dev, image_info.st_size)
        same_device({d: graph[d] for d in members}, {d: current_graph[d] for d in members})
        flags = os.O_RDWR | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
        with instance_lock(selected):
            fd = os.open(path, flags)
            with os.fdopen(fd, 'r+b', buffering=0) as target:
                opened = os.fstat(target.fileno())
                if not stat.S_ISBLK(opened.st_mode) or opened.st_rdev != info.st_rdev:
                    raise SafetyError('opened device changed; no write performed')
                capacity = struct.unpack('Q', fcntl.ioctl(target.fileno(), 0x80081272, b'\0' * 8))[0]
                if capacity != disk['size']:
                    raise SafetyError('opened device capacity changed; no write performed')
                final_graph, final_mounts, final_swaps = snapshot()
                validate_graph(final_graph, selected, final_mounts, final_swaps, source_dev, image_info.st_size)
                same_device({d: graph[d] for d in members}, {d: final_graph[d] for d in members})
                current_image = os.fstat(source.fileno())
                if any(getattr(current_image, field) != getattr(image_info, field)
                       for field in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')):
                    raise SafetyError('image changed; no write performed')
                source.seek(0)
                try:
                    copy_and_verify(source, target, image_info.st_size, sha)
                except (OSError, KeyboardInterrupt, SafetyError) as error:
                    raise SafetyError(f'write or verification failed; media may be partially written: {error}') from error
        print('Write and byte-range verification succeeded. Pi boot, enrollment and power-loss durability are not verified.')


if __name__ == '__main__':
    try:
        main()
    except (SafetyError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'flash: {error}', file=sys.stderr)
        sys.exit(1)
