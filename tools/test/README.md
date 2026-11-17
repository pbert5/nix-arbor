# Checkout tests

Run these commands from the checkout root, or invoke them by their path from
another directory.

| Command | What it runs |
| --- | --- |
| `tools/test/fast` | Offline test entry point, GitHub runner CLI, Registry lifecycle, and SSH public-key contracts using temporary fixtures. |
| `tools/test/flake` | The normal Nix flake check for the checkout, with lock-file writes disabled. |

The fast checks use Bash, jq, OpenSSH's `ssh-keygen`, and Linux shell utilities
including util-linux's `script`. The GitHub runner contract uses stubs for
Docker and GitHub. The SSH test uses Python 3 from `PATH` when available.
Otherwise, it uses `nix shell --offline` with the nixpkgs source that matches
the lock file's content hash. Both the source and the Python package must be
available in the local Nix store.

The flake check needs Nix with flakes enabled and access to cached or fetchable
locked inputs. Pass Nix options directly, for example `tools/test/flake -L` or
`tools/test/flake --no-build` for evaluation without building the checks.
Relative paths passed in options are resolved from the checkout root.

## Opt-in checks

- **Docker Compose smoke test.** Run `tests/github/runners-compose-smoke.sh`
  with a working Docker daemon and Compose. It builds an image and exercises
  a disposable project with its own volume.
- **Arbor tools.** Run `python3 tools/arbor/test.py` with Nix and the locked
  inputs available. It runs the packaged Arbor Manager against a temporary
  snapshot and Unix socket.
- **Registry acceptance.** Follow the [pure Nix harness instructions](../../tests/arbor-registry/README.md)
  for the synthetic registry and manager scenario. It uses the locked nixpkgs
  input and requires the `arbor-registry` and `arbor-manager` submodules to be
  initialized in this checkout.
- **NixOS VMs.** See the [desktop demo](../../README.md#desktop-demo-vm) and
  [Arbor Registry](../../README.md#arbor-registry-boundary) sections for checks
  that build and boot guests.
- **R640 switch contract.** `tests/r640-switch-contract.sh` expects the
  clean primary `main` checkout and the storage layout checked by the
  switch tool. The contract stubs deployment commands.
