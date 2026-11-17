#!/usr/bin/env python3
import json
import os
from pathlib import Path
import pty
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[2] / 'tools/ssh/keys'


class KeysTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.workspace = Path(temp.name)
        self.root = self.workspace / 'checkout'
        access = self.root / 'config/access'
        access.mkdir(parents=True)
        self.named = access / 'default.nix'
        self.extra = access / 'extra-keys.json'
        fixture_key = self.workspace / 'fixture'
        subprocess.run(
            ['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'fixture laptop',
             '-f', str(fixture_key)],
            check=True,
        )
        fixture_public = fixture_key.with_suffix('.pub')
        self.key = fixture_public.read_text().strip()
        self.fingerprint = subprocess.check_output(
            ['ssh-keygen', '-lf', str(fixture_public)], text=True,
        ).split()[1]
        self.named.write_text('{ exampleKeys = [ ' + json.dumps(self.key) + ' ]; }\n')
        other_key = self.workspace / 'other'
        subprocess.run(
            ['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'other-fixture',
             '-f', str(other_key)],
            check=True,
        )
        self.other = other_key.with_suffix('.pub').read_text().strip()
        self.extra.write_text(json.dumps({
            'host-a': {'ash': [self.key, self.other], 'madeline': [self.key]},
            'host-b': {'ash': [self.key]},
        }))

    def call(self, command, *args, **kwargs):
        root_args = [] if command == 'generate' else ['--root', str(self.root)]
        return subprocess.run(
            [str(TOOLS / command), *root_args, *args], cwd=self.workspace, text=True,
            capture_output=True, **kwargs,
        )

    def remove(self, *args, **kwargs):
        return self.call(
            'remove', '--host', 'host-a', '--user', 'ash', '--fingerprint', self.fingerprint,
            *args, **kwargs,
        )

    def test_list_and_find_match_public_grant_sources(self):
        listed = self.call('list')
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn('config/access/default.nix#exampleKeys', listed.stdout)
        self.assertIn('config/access/extra-keys.json', listed.stdout)
        self.assertIn('host-a/ash', listed.stdout)
        self.assertIn(self.fingerprint, listed.stdout)
        for query in ('FIXTURE LAPTOP', self.fingerprint, 'exampleKeys'):
            found = self.call('find', query)
            self.assertEqual(found.returncode, 0, found.stderr)
            self.assertIn(self.fingerprint, found.stdout)
            self.assertNotIn('other-fixture', found.stdout)
        self.assertNotEqual(self.call('find', 'no-such-key').returncode, 0)

    def test_list_defaults_to_the_checkout_containing_the_tool(self):
        shutil.copytree(TOOLS.parent, self.root / 'tools/ssh', symlinks=True)
        command = self.root / 'tools/ssh/keys/list'
        env = dict(os.environ, PATH=os.pathsep.join([str(Path(sys.executable).parent), os.environ['PATH']]))
        listed = subprocess.run([str(command)], cwd=self.workspace, text=True, capture_output=True, env=env)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn(self.fingerprint, listed.stdout)

    def test_remove_targets_only_exact_host_user_and_fingerprint(self):
        before_named = self.named.read_bytes()
        dry_run = self.remove('--dry-run')
        self.assertEqual(dry_run.returncode, 0, dry_run.stderr)
        self.assertIn(self.fingerprint, dry_run.stdout)
        self.assertIn(self.key, self.extra.read_text())
        result = self.remove('--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(self.fingerprint, result.stdout)
        self.assertEqual(json.loads(self.extra.read_text()), {
            'host-a': {'ash': [self.other], 'madeline': [self.key]},
            'host-b': {'ash': [self.key]},
        })
        self.assertEqual(self.named.read_bytes(), before_named)
        self.assertNotEqual(self.remove('--yes').returncode, 0)

    def test_remove_requires_confirmation_and_can_cancel(self):
        before = self.extra.read_bytes()
        result = self.remove(input='y\n')
        self.assertNotEqual(result.returncode, 0)
        master, slave = pty.openpty()
        try:
            os.write(master, b'n\n')
            cancelled = self.remove(stdin=slave, timeout=10)
        finally:
            os.close(slave)
            os.close(master)
        self.assertEqual(cancelled.returncode, 0, cancelled.stderr)
        self.assertIn('Cancelled', cancelled.stdout)
        self.assertEqual(self.extra.read_bytes(), before)

    def test_remove_requires_exact_row_when_fingerprint_is_shared(self):
        ca = self.workspace / 'ca'
        subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(ca)], check=True)
        subprocess.run(
            ['ssh-keygen', '-q', '-s', str(ca), '-I', 'disposable', '-n', 'fixture',
             str(self.workspace / 'fixture.pub')],
            check=True,
        )
        cert = (self.workspace / 'fixture-cert.pub').read_text().strip()
        self.extra.write_text(json.dumps({'host-a': {'ash': [self.key, cert]}}))
        before = self.extra.read_bytes()
        ambiguous = self.remove('--yes')
        self.assertNotEqual(ambiguous.returncode, 0)
        self.assertEqual(self.extra.read_bytes(), before)

        master, slave = pty.openpty()
        try:
            os.write(master, b'2\ny\n')
            removed = self.call('remove', stdin=slave, timeout=10)
        finally:
            os.close(slave)
            os.close(master)
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertEqual(json.loads(self.extra.read_text()), {'host-a': {'ash': [self.key]}})

    def add_key(self, key):
        machine = self.root / 'config/machines/host-c'
        machine.mkdir(parents=True, exist_ok=True)
        (machine / 'default.nix').touch()
        return subprocess.run(
            [sys.executable, str(TOOLS.parent / 'add-key'), '--root', str(self.root)],
            input=f'{key}\n1\n0\ny\n', cwd=self.workspace, text=True, capture_output=True,
        )

    def test_add_key_accepts_a_unicode_comment(self):
        key = ' '.join(self.key.split()[:2]) + ' fixture 👩‍💻'
        saved = self.add_key(key)
        self.assertEqual(saved.returncode, 0, saved.stderr)
        data = json.loads(self.extra.read_text())
        self.assertEqual(data['host-c']['ash'], [key])
        found = self.call('find', '👩‍💻')
        self.assertEqual(found.returncode, 0, found.stderr)
        self.assertIn('host-c/ash', found.stdout)

    def test_key_fields_require_openssh_space_or_tab_separators(self):
        algorithm, rest = self.key.split(maxsplit=1)
        tabbed_key = algorithm + '\t' + rest
        self.assertEqual(self.add_key(tabbed_key).returncode, 0)
        before = self.extra.read_bytes()
        for separator in ('\v', '\u00a0', '\u2028'):
            with self.subTest(separator=separator):
                malformed = algorithm + separator + rest
                self.assertNotEqual(self.add_key(malformed).returncode, 0)
                self.assertEqual(self.extra.read_bytes(), before)
                self.extra.write_text(json.dumps({'host-c': {'ash': [malformed]}}))
                self.assertNotEqual(self.call('list').returncode, 0)
                self.extra.write_bytes(before)

    def test_malformed_grants_fail_before_writing(self):
        for data in ('not JSON', '{"host-a":{"ash":"bad shape"}}',
                     '{"host-a":{"ash":["ssh-ed25519 invalid"]}}',
                     '{"host-a":{},"host-a":{}}',
                     json.dumps({'host-a': {'ash': ['ssh-fake ' + self.key]}})):
            with self.subTest(data=data):
                self.extra.write_text(data)
                self.assertNotEqual(self.call('list').returncode, 0)
                self.assertNotEqual(self.remove('--yes').returncode, 0)
                self.assertEqual(self.extra.read_text(), data)

    def test_generate_ed25519_and_refuse_overwrite(self):
        output = self.workspace / 'new'
        public = output.with_suffix('.pub')
        public.write_text('existing public')
        refused = self.call('generate', '--output', str(output), '--no-passphrase')
        self.assertNotEqual(refused.returncode, 0)
        self.assertFalse(output.exists())
        self.assertEqual(public.read_text(), 'existing public')
        public.unlink()
        generated = self.call(
            'generate', '--output', str(output), '--no-passphrase', '--comment', 'fixture only',
        )
        self.assertEqual(generated.returncode, 0, generated.stderr)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertTrue(public.read_text().startswith('ssh-ed25519 '))
        self.assertTrue(public.read_text().strip().endswith(' fixture only'))
        private_before = output.read_bytes()
        public_before = public.read_bytes()
        self.assertNotEqual(
            self.call('generate', '--output', str(output), '--no-passphrase').returncode, 0,
        )
        self.assertEqual(output.read_bytes(), private_before)
        self.assertEqual(public.read_bytes(), public_before)

    def generate_with_passphrase(self, output, passphrase, after_prompt=None):
        master, slave = pty.openpty()
        try:
            with subprocess.Popen(
                [str(TOOLS / 'generate'), '--output', str(output)],
                cwd=self.workspace, stdin=slave, stdout=slave, stderr=slave, start_new_session=True,
            ) as process:
                try:
                    for prompt in (b'Enter passphrase', b'Enter same passphrase'):
                        messages = b''
                        while prompt not in messages:
                            ready, _, _ = select.select([master], [], [], 10)
                            self.assertTrue(ready, messages)
                            messages += os.read(master, 4096)
                        if prompt == b'Enter passphrase' and after_prompt is not None:
                            after_prompt()
                        os.write(master, (passphrase + '\n').encode())
                    return process.wait(timeout=20)
                finally:
                    if process.poll() is None:
                        process.kill()
        finally:
            os.close(slave)
            os.close(master)

    def test_generation_supports_an_interactive_passphrase(self):
        output = self.workspace / 'encrypted'
        passphrase = 'disposable fixture passphrase'
        self.assertEqual(self.generate_with_passphrase(output, passphrase), 0)
        wrong = subprocess.run(['ssh-keygen', '-y', '-P', '', '-f', str(output)], capture_output=True)
        self.assertNotEqual(wrong.returncode, 0)
        unlocked = subprocess.run(
            ['ssh-keygen', '-y', '-P', passphrase, '-f', str(output)], text=True, capture_output=True,
        )
        self.assertEqual(unlocked.returncode, 0, unlocked.stderr)
        self.assertTrue(unlocked.stdout.startswith('ssh-ed25519 '))

    def test_generate_rechecks_destination_after_passphrase_prompt(self):
        destination = self.workspace / 'destination'
        destination.mkdir()
        output = destination / 'new'

        def init_checkout():
            subprocess.run(['git', 'init', '-q', str(destination)], check=True)

        result = self.generate_with_passphrase(output, 'fixture secret', after_prompt=init_checkout)
        self.assertNotEqual(result, 0)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix('.pub').exists())

    def test_generate_refuses_checkout_and_implicit_empty_passphrase(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        output = self.root / 'new'
        result = self.call('generate', '--output', str(output), '--no-passphrase')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        output = self.workspace / 'new'
        result = self.call('generate', '--output', str(output), input='\n\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
