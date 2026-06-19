# Bootstrap Toolkit

This directory holds the bootstrap tooling and its operator-local guidance.

Use the docs here when you want the implementation-facing view of the bootstrap
flow. Use [`docs/cluster-ops/`](/work/flake/docs/cluster-ops/README.md)
when you want the broader fleet/operator handbook.

## Tools

- [`nbootstrap.py`](/work/flake/bootstrap/nbootstrap.py)
  umbrella CLI for installer build/write, host bootstrap, and validation
- [`yggdrasil-bootstrap.py`](/work/flake/bootstrap/yggdrasil-bootstrap.py)
  low-level host identity enrollment and bootstrap metadata writer
- [`live-installer.py`](/work/flake/bootstrap/live-installer.py)
  installer image build/write helper
- [`bootstrap-validate.py`](/work/flake/bootstrap/bootstrap-validate.py)
  preflight validator for host bootstrap metadata, leader access, and generated
  deploy targets

## Most Useful Commands

```bash
nix run .#bootstrap-validate
nix run .#nbootstrap -- validate
nix run .#nbootstrap -- host bootstrap --host t320-0 --dry-run
nix run .#deploy-rs -- .#t320-0
```

## Local Docs

- [`validation.md`](/work/flake/bootstrap/validation.md)
  what the validator checks and how to use it before rollout
- [`secrets.md`](/work/flake/bootstrap/secrets.md)
  the repo's agenix-based secret-management foundation and recipient model
