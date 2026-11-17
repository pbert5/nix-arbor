#!/usr/bin/env python3
"""Build and personalize a Raspberry eVolver image (work in progress)."""
import argparse
import configparser
import getpass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
import re
import shlex
import signal
import sys
import stat
import warnings


KEY = re.compile(r'tskey-auth-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\Z')


def parse_key(paste):
    """Accept a key or the documented command; never execute the pasted text."""
    # Reject shell expansions even inside quotes. Only backslash-newline is allowed.
    if any(c in paste for c in '$`\r'):
        raise ValueError('Unsupported key input')
    paste = paste.replace('\\\n', '')
    if '\n' in paste:
        raise ValueError('Unsupported key input')
    paste = paste.strip()
    if KEY.fullmatch(paste):
        return paste
    try:
        lexer = shlex.shlex(paste, posix=True, punctuation_chars='|&;<>')
        lexer.whitespace_split = True
        lexer.commenters = ''
        tokens = list(lexer)
    except ValueError:
        raise ValueError('Unsupported key input') from None
    prefix = ['curl', '-fsSL', 'https://tailscale.com/install.sh', '|', 'sh',
              '&&', 'sudo', 'tailscale', 'up']
    if tokens[:len(prefix)] != prefix:
        raise ValueError('Unsupported key input')
    args = tokens[len(prefix):]
    if len(args) == 1 and args[0].startswith('--auth-key='):
        key = args[0][len('--auth-key='):]
    elif len(args) == 2 and args[0] == '--auth-key':
        key = args[1]
    else:
        raise ValueError('Unsupported key input')
    if not KEY.fullmatch(key):
        raise ValueError('Unsupported key input')
    return key



def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_clean_artifact(source, destination, revision, lock_hash):
    """Copy a raw clean image to a private directory and write its manifest."""
    compressed = source.name.endswith('.zst')
    if compressed:
        details = subprocess.check_output(['zstd', '-lv', str(source)], text=True, stderr=subprocess.STDOUT)
        match = re.search(r'^Decompressed Size: .*\((\d+) B\)$', details, re.MULTILINE)
        if not match or not re.search(r'^# Zstandard Frames: 1$', details, re.MULTILINE):
            raise OSError('Cannot establish the uncompressed size of the image')
        size = int(match.group(1))
    else:
        size = source.stat().st_size
    if not size:
        raise OSError('Image is empty')
    if shutil.disk_usage(destination.parent).free < size * 2 + 1024**3:
        raise OSError('Insufficient space for the image and verification staging')
    manifest_path = Path(str(destination) + '.json')
    created_image = False
    created_manifest = False
    try:
        with destination.open('xb') as dst:
            created_image = True
            os.chmod(destination, 0o600)
            if compressed:
                subprocess.run(['zstd', '-q', '-d', '-c', str(source)], stdout=dst, check=True)
            else:
                with source.open('rb') as src:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
        result_hash = digest(destination)
        if (not compressed and digest(source) != result_hash) or destination.stat().st_size != size:
            raise OSError('Image copy verification failed')
        manifest = {'schema_version': 1, 'model': 'Raspberry Pi 4',
                    'hostname': 'raspberry-evolver', 'source_revision': revision,
                    'lock_sha256': lock_hash, 'clean_sha256': result_hash,
                    'result_size': size, 'result_sha256': result_hash,
                    'personalized': False}
        with manifest_path.open('x') as stream:
            created_manifest = True
            os.chmod(manifest_path, 0o600)
            json.dump(manifest, stream, indent=2)
            stream.write('\n')
        return manifest
    except BaseException:
        if created_manifest:
            manifest_path.unlink(missing_ok=True)
        if created_image:
            destination.unlink(missing_ok=True)
        raise



def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate manifest key')
        result[key] = value
    return result


def verify_clean_artifact(path):
    manifest_path = Path(str(path) + '.json')
    if path.is_symlink() or manifest_path.is_symlink() or not path.is_file() or not manifest_path.is_file():
        raise ValueError('Clean image and adjacent manifest must be regular files')
    if manifest_path.stat().st_size > 65536:
        raise ValueError('Clean image manifest is too large')
    try:
        manifest = json.loads(manifest_path.read_text(), object_pairs_hook=unique_json_object)
        valid = (type(manifest) is dict
                 and set(manifest) == {'schema_version', 'model', 'hostname', 'source_revision',
                                      'lock_sha256', 'clean_sha256', 'result_size', 'result_sha256', 'personalized'} and manifest.get('schema_version') == 1
                 and manifest.get('model') == 'Raspberry Pi 4'
                 and manifest.get('hostname') == 'raspberry-evolver'
                 and manifest.get('personalized') is False
                 and type(manifest.get('result_size')) is int
                 and manifest['result_size'] > 0
                 and all(isinstance(manifest.get(k), str) and re.fullmatch(r'[0-9a-f]{64}', manifest[k])
                         for k in ('lock_sha256', 'clean_sha256', 'result_sha256'))
                 and isinstance(manifest.get('source_revision'), str)
                 and re.fullmatch(r'(?:[0-9a-f]{40}|[0-9a-f]{64})', manifest['source_revision'])
                 and manifest['clean_sha256'] == manifest['result_sha256'])
    except (ValueError, UnicodeError):
        valid = False
    if not valid or path.stat().st_size != manifest['result_size'] or digest(path) != manifest['result_sha256']:
        raise ValueError('Clean image manifest or digest is invalid')
    return manifest



def portable_wifi(text):
    """Transfer one simple WPA-PSK profile, rejecting unsupported security."""
    config = configparser.ConfigParser(interpolation=None, strict=True)
    config.optionxform = str
    try:
        config.read_string(text)
        allowed_sections = {'connection', 'wifi', 'wifi-security', 'ipv4', 'ipv6', 'proxy'}
        if config.defaults() or not set(config.sections()) <= allowed_sections:
            raise ValueError
        connection, wifi, security = config['connection'], config['wifi'], config['wifi-security']
        if connection.get('type') not in ('wifi', '802-11-wireless'):
            raise ValueError
        if set(connection) - {'id', 'uuid', 'type', 'interface-name', 'autoconnect',
                              'autoconnect-priority', 'timestamp', 'permissions', 'stable-id'}:
            raise ValueError
        if set(wifi) - {'ssid', 'mode', 'mac-address', 'cloned-mac-address', 'mac-address-randomization',
                        'powersave', 'seen-bssids', 'band', 'channel'}:
            raise ValueError
        if set(security) - {'key-mgmt', 'psk', 'psk-flags'}:
            raise ValueError
        ssid, psk = wifi['ssid'], security['psk']
        if (wifi.get('mode', 'infrastructure') != 'infrastructure'
                or security.get('key-mgmt') != 'wpa-psk'
                or security.get('psk-flags', '0') != '0'
                or not 1 <= len(ssid) <= 32
                or any(ord(c) < 32 or ord(c) > 126 or c in '\\;' for c in ssid)
                or any(ord(c) < 32 or ord(c) > 126 or c == '\\' for c in psk)
                or not (8 <= len(psk) <= 63 or re.fullmatch('[0-9a-fA-F]{64}', psk))):
            raise ValueError
    except (configparser.Error, KeyError, ValueError):
        raise ValueError('Unsupported Wi-Fi profile; provide a simple WPA-PSK profile with stored password') from None
    return (f'[connection]\nid=raspberry-evolver-wifi\nuuid={uuid.uuid4()}\ntype=wifi\n'
            f'[wifi]\nmode=infrastructure\nssid={ssid}\n[wifi-security]\nkey-mgmt=wpa-psk\npsk={psk}\n'
            '[ipv4]\nmethod=auto\n[ipv6]\nmethod=auto\n')

def root_partition(path):
    """Find the unique NIXOS_SD ext4 filesystem using the partition table."""
    raw = subprocess.check_output(['sfdisk', '--json', str(path)], stderr=subprocess.DEVNULL)
    try:
        table = json.loads(raw)['partitiontable']
        sector_size = table['sectorsize']
        if type(sector_size) is not int or sector_size <= 0:
            raise ValueError
        candidates = []
        intervals = []
        for entry in table['partitions']:
            start, size = entry['start'] * sector_size, entry['size'] * sector_size
            if start < sector_size or size <= 0 or start + size > path.stat().st_size:
                raise ValueError
            if any(start < end and begin < start + size for begin, end in intervals):
                raise ValueError
            intervals.append((start, start + size))
            probe = subprocess.run(['blkid', '-p', '-o', 'export', '-O', str(start),
                                    '-S', str(size), str(path)], capture_output=True, text=True)
            fields = dict(line.split('=', 1) for line in probe.stdout.splitlines() if '=' in line)
            if probe.returncode == 0 and fields.get('TYPE') == 'ext4' and fields.get('LABEL') == 'NIXOS_SD':
                candidates.append((start, size))
        if len(candidates) != 1:
            raise ValueError
        return candidates[0]
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise ValueError('Image must contain exactly one bounded NIXOS_SD ext4 partition') from None


def debugfs(partition, command, cwd):
    result = subprocess.run(['debugfs', '-w', '-R', command, str(partition)],
                            cwd=cwd, capture_output=True, text=True, check=True)
    # debugfs can return zero even when a command failed.
    lines = result.stderr.splitlines()
    if any(not line.startswith('debugfs ') for line in lines):
        raise ValueError('Could not safely modify the image filesystem')
    return result.stdout



def optional_stat(partition, path, cwd):
    result = subprocess.run(['debugfs', '-R', 'stat ' + path, str(partition)],
                            cwd=cwd, capture_output=True, text=True, check=True)
    lines = [line for line in result.stderr.splitlines() if not line.startswith('debugfs ')]
    if lines == [path + ': File not found by ext2_lookup ']:
        return None
    if lines or not result.stdout.startswith('Inode: '):
        raise ValueError('Could not inspect source identity')
    return result.stdout


def ensure_directory(partition, path, cwd):
    info = optional_stat(partition, path, cwd)
    if info is None:
        debugfs(partition, 'mkdir ' + path, cwd)
        info = debugfs(partition, 'stat ' + path, cwd)
    if 'Type: directory' not in info or 'User:     0   Group:     0' not in info:
        raise ValueError('Image has unsupported filesystem structure')


def reject_source_identity(partition, cwd):
    for path in ('/var/lib/tailscale', '/var/lib/private/tailscale',
                 '/var/lib/raspberry-evolver', '/var/lib/dbus/machine-id'):
        if optional_stat(partition, path, cwd) is not None:
            raise ValueError('Source image contains existing device state')
    machine_id = optional_stat(partition, '/etc/machine-id', cwd)
    if machine_id is not None and ('Type: regular' not in machine_id or not re.search(r'(?m)^User:\s+0\s+Group:\s+0\s+Project:\s+\d+\s+Size:\s+0\s*$', machine_id)):
        raise ValueError('Source image contains an existing machine identity')
    ssh = optional_stat(partition, '/etc/ssh', cwd)
    if ssh is not None:
        if 'Type: directory' not in ssh:
            raise ValueError('Source SSH directory is unsupported')
        listing = debugfs(partition, 'ls -p /etc/ssh', cwd)
        if 'ssh_host_' in listing:
            raise ValueError('Source image contains existing SSH host identity')

def personalize(source, destination, key, wifi=None):
    """Experimental offline image operation; callers must supply private staging."""
    if not KEY.fullmatch(key):
        raise ValueError('Unsupported key input')
    if wifi is not None:
        wifi = portable_wifi(wifi)
    manifest = verify_clean_artifact(source)
    start, size = root_partition(source)
    if shutil.disk_usage(destination.parent).free < source.stat().st_size + size + 1024**3:
        raise OSError('Insufficient space for private image and partition staging')
    created = False
    manifest_path = Path(str(destination) + '.json')
    created_manifest = False
    try:
        with tempfile.TemporaryDirectory(prefix='staging-', dir=destination.parent) as tmp:
            stage = Path(tmp)
            partition = stage / 'partition'
            key_path = stage / 'key'
            with key_path.open('x') as stream:
                os.chmod(key_path, 0o600)
                stream.write(key + '\n')
            if wifi is not None:
                with (stage / 'wifi').open('x') as stream:
                    os.chmod(stage / 'wifi', 0o600)
                    stream.write(wifi)
            with source.open('rb') as src, destination.open('xb') as dst:
                created = True
                os.chmod(destination, 0o600)
                shutil.copyfileobj(src, dst, 1024 * 1024)
            if digest(destination) != manifest['result_sha256']:
                raise ValueError('Clean image changed during copying')
            with destination.open('rb') as src, partition.open('xb') as dst:
                os.chmod(partition, 0o600)
                src.seek(start)
                remaining = size
                while remaining:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise OSError('Truncated partition')
                    dst.write(chunk)
                    remaining -= len(chunk)
            subprocess.run(['e2fsck', '-fn', str(partition)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            reject_source_identity(partition, stage)
            for path in ('/var', '/var/lib'):
                ensure_directory(partition, path, stage)
            for path in ('/var/lib/raspberry-evolver', '/var/lib/raspberry-evolver/bootstrap'):
                debugfs(partition, 'mkdir ' + path, stage)
                debugfs(partition, 'set_inode_field ' + path + ' mode 040700', stage)
                info = debugfs(partition, 'stat ' + path, stage)
                if 'Type: directory' not in info or 'Mode:  0700' not in info or 'User:     0   Group:     0' not in info:
                    raise ValueError('Could not verify image directory permissions')
            target = '/var/lib/raspberry-evolver/bootstrap/tailscale.authkey'
            debugfs(partition, 'write key ' + target, stage)
            debugfs(partition, 'set_inode_field ' + target + ' mode 0100600', stage)
            info = debugfs(partition, 'stat ' + target, stage)
            if 'Type: regular' not in info or 'Mode:  0600' not in info or 'User:     0   Group:     0' not in info:
                raise ValueError('Could not verify image key permissions')
            if debugfs(partition, 'cat ' + target, stage) != key + '\n':
                raise ValueError('Could not verify image key content')
            if wifi is not None:
                for path in ('/etc', '/etc/NetworkManager'):
                    ensure_directory(partition, path, stage)
                connection_dir = '/etc/NetworkManager/system-connections'
                debugfs(partition, 'mkdir ' + connection_dir, stage)
                debugfs(partition, 'set_inode_field ' + connection_dir + ' mode 040700', stage)
                info = debugfs(partition, 'stat ' + connection_dir, stage)
                if 'Type: directory' not in info or 'Mode:  0700' not in info or 'User:     0   Group:     0' not in info:
                    raise ValueError('Could not verify Wi-Fi directory permissions')
                wifi_target = connection_dir + '/raspberry-evolver.nmconnection'
                debugfs(partition, 'write wifi ' + wifi_target, stage)
                debugfs(partition, 'set_inode_field ' + wifi_target + ' mode 0100600', stage)
                info = debugfs(partition, 'stat ' + wifi_target, stage)
                if 'Type: regular' not in info or 'Mode:  0600' not in info or 'User:     0   Group:     0' not in info:
                    raise ValueError('Could not verify Wi-Fi file permissions')
                if debugfs(partition, 'cat ' + wifi_target, stage) != wifi:
                    raise ValueError('Could not verify Wi-Fi content')
            subprocess.run(['e2fsck', '-fn', str(partition)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            with destination.open('r+b') as dst, partition.open('rb') as src:
                dst.seek(start)
                shutil.copyfileobj(src, dst, 1024 * 1024)
            manifest.update(personalized=True, result_size=destination.stat().st_size,
                            result_sha256=digest(destination))
            with manifest_path.open('x') as stream:
                created_manifest = True
                os.chmod(manifest_path, 0o600)
                json.dump(manifest, stream, indent=2)
                stream.write('\n')
    except BaseException:
        if created_manifest:
            manifest_path.unlink(missing_ok=True)
        if created:
            destination.unlink(missing_ok=True)
        raise

def private_directory():
    state = os.environ.get('XDG_STATE_HOME')
    if state and not Path(state).is_absolute():
        raise ValueError('XDG_STATE_HOME must be an absolute path')
    base = (Path(state) if state else Path.home() / '.local' / 'state') / 'raspberry-evolver'
    for path in reversed(base.parents):
        if path.is_symlink():
            raise OSError('State directory has a symlink in its path')
    if base.is_symlink() or str(base).startswith('/nix/store/'):
        raise OSError('Unsafe state directory')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    if base.stat().st_uid != os.getuid() or base.stat().st_mode & 0o077:
        raise OSError('State directory must be owned by the user and mode 0700')
    check = subprocess.run(['git', '-C', str(base), 'rev-parse', '--show-toplevel'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if check.returncode == 0:
        raise OSError('State directory must be outside Git checkouts')
    return Path(tempfile.mkdtemp(prefix='image-', dir=base))


def build_clean():
    repo = Path(__file__).resolve().parents[2]
    if subprocess.run(['git', '-C', str(repo), 'status', '--porcelain', '--untracked-files=no'],
                      capture_output=True, check=True).stdout:
        raise OSError('Commit tracked changes before building so provenance is reproducible')
    revision = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    lock_hash = digest(repo / 'flake.lock')
    result = subprocess.check_output(['nix', 'build', '--no-link', '--print-out-paths',
                                      str(repo) + '#raspberry-evolver-image'], text=True)
    outputs = result.strip().splitlines()
    if len(outputs) != 1:
        raise OSError('Expected one Nix image output')
    images = list(Path(outputs[0]).rglob('*.img')) + list(Path(outputs[0]).rglob('*.img.zst'))
    if len(images) != 1:
        raise OSError('Expected exactly one .img or .img.zst in Nix output')
    directory = private_directory()
    try:
        destination = directory / 'clean.img'
        write_clean_artifact(images[0], destination, revision, lock_hash)
    except BaseException:
        directory.rmdir()
        raise
    print(f'Clean image: {destination}')
    print(f'Manifest: {destination}.json')
    return destination


def prompt_key():
    print('Prefer a one-use, non-ephemeral Tailscale key. Approval, expiry and consumption depend on your tailnet settings.', file=sys.stderr)
    lines = []
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        while True:
            line = getpass.getpass('Paste auth key or install command: ' if not lines else 'Continue paste: ')
            lines.append(line)
            if sum(map(len, lines)) > 8192:
                raise ValueError('Key input is too long')
            if not line.endswith('\\'):
                break
    return parse_key('\n'.join(lines))


def read_wifi(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Wi-Fi profile path must not contain symlinks')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()) or info.st_mode & 0o077 or info.st_size > 65536:
            raise ValueError('Wi-Fi profile must be an owner-only regular file')
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            fd = -1
            return portable_wifi(stream.read(65537))
    finally:
        if fd >= 0:
            os.close(fd)


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--build-only', action='store_true', help='build a clean image without credentials')
    group.add_argument('--from', dest='source', metavar='CLEAN_IMAGE', help='personalize a verified clean image')
    parser.add_argument('--wifi-file', metavar='PROFILE', help='import one owner-only WPA-PSK NetworkManager profile')
    args = parser.parse_args()
    if args.build_only and args.wifi_file:
        parser.error('--wifi-file cannot be used with --build-only')
    try:
        if args.build_only:
            build_clean()
            return 0
        source = Path(args.source) if args.source else build_clean()
        verify_clean_artifact(source)
        for tool in ('sfdisk', 'blkid', 'debugfs', 'e2fsck'):
            if not shutil.which(tool):
                raise OSError('Missing required image tool: ' + tool)
        root_partition(source)
        wifi = read_wifi(args.wifi_file) if args.wifi_file else None
        directory = private_directory()
        try:
            key = prompt_key()
            destination = directory / 'personalized.img'
            personalize(source, destination, key, wifi)
        except BaseException:
            (directory / 'personalized.img.json').unlink(missing_ok=True)
            (directory / 'personalized.img').unlink(missing_ok=True)
            directory.rmdir()
            raise
        print(f'Personalized image: {destination}')
        print(f'Manifest: {destination}.json')
        print('This private image remains sensitive after enrollment; delete it when no longer needed.')
        return 0
    except (OSError, ValueError, subprocess.SubprocessError, getpass.GetPassWarning, EOFError):
        print('Image operation failed. Check the clean image, private storage, tools, terminal and selected profile.', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Image operation interrupted; check private state for incomplete output.', file=sys.stderr)
        return 1


def main():
    signals = (signal.SIGTERM, signal.SIGHUP)
    previous = {number: signal.getsignal(number) for number in signals}

    def terminate(_number, _frame):
        # Avoid a second termination interrupting sensitive-file cleanup.
        for number in signals:
            signal.signal(number, signal.SIG_IGN)
        raise KeyboardInterrupt

    try:
        for number in signals:
            signal.signal(number, terminate)
        try:
            return _main()
        except KeyboardInterrupt:
            print('Image operation interrupted; check private state for incomplete output.', file=sys.stderr)
            return 1
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    sys.exit(main())
