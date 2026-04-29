# FossilSafe Experiment

This experiment runs the local FossilSafe fork without enabling the managed
NixOS service.

It reads host settings from the main repo's `inventory/hosts.nix` and
`inventory/ports.nix`, writes a generated config into a user-local state
directory, optionally applies the inventory bootstrap payload, and then starts
`fossilsafe` directly.

## Why this exists

- keep `storage/tape` active on the host
- leave `org.storage.tape.manager` unset so the systemd service stays off
- iterate on FossilSafe without a full host rebuild/switch
- reuse the same device paths, endpoint settings, and bootstrap data from
  inventory

## Usage

From the repo root:

```bash
nix run ./experiments/fossilsafe -- --flake /work/flake --host desktoptoodle
```

Print the rendered config instead of launching:

```bash
nix run ./experiments/fossilsafe -- --flake /work/flake --host desktoptoodle --print-config
```

Pass extra FossilSafe arguments after `--`:

```bash
nix run ./experiments/fossilsafe -- --flake /work/flake --host desktoptoodle -- --help
```

## Runtime state

By default the experiment keeps runtime data under:

- `~/.local/state/fossilsafe-experiments/<host>`

Override that with `--state-dir` when you want multiple sandboxes.

## Notes

- This launcher does **not** register or start a systemd service.
- Inventory bootstrap data is applied on each run unless `--skip-bootstrap` is
  used.
- Hardware access still depends on the current user being able to reach the tape
  devices.
