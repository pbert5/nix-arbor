# Checkout-local Arbor tools

Run the examples from the checkout root. From another directory, invoke the
script by its path, for example `/path/to/nix-arbor/tools/test/fast`. Each script
that uses the checkout resolves it from its own location. Use `--help` on any
entry point for its arguments.

In VS Code, open that checkout and choose **Tasks: Run Task**. Look for
`Arbor: …` tasks and start with the check, status, list, or preview action.
Switches and deletions have their own tasks. VS Code needs the same tools on
its `PATH` as the command-line entry points.

## Environment and tests

| Command | Effect |
| --- | --- |
| `tools/env/setup --status` | Read-only checkout and tool preflight. Add `--json` for machine-readable output. |
| `tools/env/setup` | Initialize direct submodules at their recorded revisions and check the dev shell. |
| `tools/env/shell --check` | Validate the dev shell without running its shell hook. |
| `tools/env/shell` | Enter the dev shell. Use `tools/env/shell -- COMMAND ARG` to run a command in it. |
| `tools/test/fast` | Run fast, host-independent checkout tests. |
| `tools/test/flake` | Run the normal `nix flake check` with lock-file writes disabled. |

See the [checkout test guide](test/README.md) for prerequisites and opt-in
Docker, VM, and other checks.

## Registry identities

Run `tools/arbor/registry status r640-0` or `tools/arbor/registry inspect eVolver`
from either host’s checkout for that host, or select eVolver remotely from r640-0. The [local Registry runbook](arbor/README.md#local-registry)
covers service checks, self-initialization, summaries and restart verification.

## Machine rebuilds

Use `switch --check` on the target host and `remote-switch --check` to check
over SSH. Both accept `--dry-run` for a build without activation. Running
either command without arguments requests activation.

| Machine | Local entry point | Remote entry point |
| --- | --- | --- |
| `r640-0` | `tools/machines/r640-0/switch` | `tools/machines/r640-0/remote-switch` |
| `eVolver` | `tools/machines/evolver/switch` | `tools/machines/evolver/remote-switch` |

On `r640-0`, the legacy switch guard requires the clean primary `main`
checkout and its expected storage mounts. The remote command uses SSH alias
`r640-0` and requires the remote clean primary `main` to match the invoking
checkout's committed HEAD. Its dry run builds on `r640-0`.

The eVolver remote command uses `root-evolver` and the invoking checkout's
flake. Its dry run builds the closure locally. Both remote commands rely on
the normal OpenSSH host-key checks when connecting.

## Windows private Yggdrasil guest

See the [Windows guest guide](yggdrasil/README.md) for identity, pinned peer,
peer status, SSH, and host authorization steps.

## SSH public grants and keypairs

```sh
tools/ssh/keys/list
tools/ssh/keys/find -- QUERY
tools/ssh/keys/remove --host HOST --user USER --fingerprint SHA256:FINGERPRINT --dry-run
```

The SSH commands use Python 3 and OpenSSH. The `keys/` commands use the
checkout's locked Nixpkgs for Python if it is missing from `PATH`.
`tools/ssh/add-key` needs Python on `PATH`. Listing and searching also use
Nix to evaluate the named sets. The inventory shows named public-key sets from
`config/access/default.nix` and extra public grants by host and user from
`config/access/extra-keys.json`.
Host configuration controls where named sets are granted. `tools/ssh/add-key`
adds public keys to the extra grants after review in the terminal. Removal
edits only the extra grants. Run `tools/ssh/keys/remove` in a terminal to
select and confirm interactively, or add `--yes` in place of `--dry-run` to
confirm an exact host, user, and full fingerprint.

Use `tools/ssh/keys/generate --output PATH` in a terminal to create a local
Ed25519 keypair in an existing directory outside Git checkouts. OpenSSH prompts
for the passphrase and the tool refuses to overwrite either output file. Use
only the `.pub` file for grants. Bootstrap access with an already authorized
identity or console access to deploy the reviewed declaration. Verify the new
login from a separate session before retiring the old access. See the
[SSH operator guide](../docs/ssh.md) for aliases and identity provisioning.

## Codex and VS Code pins

```sh
tools/software/update/codex preview --host r640-0
tools/software/update/vscode preview --host desktoptoodle
```

For either command, `update --host HOST --revision NIXPKGS_SHA` takes a full
40-character upstream Nixpkgs commit and checks the resulting package version
before updating the checkout. Review and commit the flake diff before any
separate switch. The eVolver Codex update also requires `--allow-host-nixpkgs`
because it can change other packages and configurations that use the shared pin.

The `r640-0` Codex update changes the dedicated `codex-nixpkgs` pin. After
review and commit, run `tools/software/update/codex switch --host r640-0`
separately on `r640-0` from the canonical clean `main` checkout. For eVolver,
the same `switch --host eVolver` action invokes the local guarded system switch.

The VS Code update changes the nested AshDesktopApps unstable Nixpkgs input
shared by the optional editor and other unstable desktop apps. Desktop core
omits the editor. The Remote-SSH module on `r640-0` and `eVolver` supplies
compatibility libraries, and the desktop client supplies the remote runtime.
Run `tools/software/update/vscode switch --host HOST` on the selected host to
build or refresh `result-vscode/bin/code` in the invoking checkout. Launch that
binary to use the selected pin with your existing profiles.

## Cleanup

- `tools/worktrees/clean` previews linked worktrees and explains what keeps
  them ineligible. Confirm a worktree is inactive before passing its exact
  path to `tools/worktrees/clean --apply PATH`. Preview shell-escapes paths
  for Bash. In the VS Code prompt, enter the literal absolute path with its
  spaces, such as `/path/to/my worktree`. Apply rechecks eligibility and
  preserves branch refs. With a remote configured, the commit must be present
  in both local `main` and cached `origin/main`.
- `tools/store/clean` lists registered Nix store paths, with likely smoke,
  test, and VM outputs first. Liveness is unknown. `tools/store/clean --apply
  /nix/store/HASH-NAME` requests deletion of the exact path. The local Nix
  daemon checks roots and referrers at deletion time. If you pass multiple
  explicit paths on the command line, deletion can partially succeed. Deletion
  can also trigger daemon housekeeping of reserved GC space, stale root records,
  and unused store links.
