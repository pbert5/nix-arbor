# FossilSafe

Local package: `fossilsafe`

Companion commands:

- `fossilsafe`
- `fossilsafe-bootstrap`
- `fossilsafe-cli`
- `fossilsafe-smoke-test`

## What We Added

- Feature-local flake under
  [`fruits/fossilsafe/flake.nix`](/work/flake/fruits/fossilsafe/flake.nix)
- Vendored fork source under
  [`fruits/fossilsafe/FOSSILSAFE`](/work/flake/fruits/fossilsafe/FOSSILSAFE)
- Nix package and NixOS module under
  [`fruits/fossilsafe/nix`](/work/flake/fruits/fossilsafe/nix)
- Frontend built from the forked `frontend/package-lock.json`

## Integration Notes

- Host-specific FossilSafe settings now live in
  [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix) under
  `org.storage.tape.fossilsafe`.
- The `storage/tape` dendrite plus `fossilsafe` fruit now replace the old
  feature-flake import path. The service only enables when
  `org.storage.tape.manager` is set to `fossilsafe`; omitting the manager keeps
  the inventory data in place while leaving the systemd service off.
- When the service is enabled, `/etc/fossilsafe/config.json` is rendered from
  Nix instead of being treated as installer-owned mutable state.
- The package still falls back to XDG-backed config and state for ad-hoc
  interactive runs outside the NixOS service path.
- `experiments/fossilsafe` now provides the preferred `nix run` path for local
  iteration against inventory-derived settings without switching the host.
- The default listen port comes from
  [`inventory/ports.nix`](/work/flake/inventory/ports.nix).
- Port inventory now also carries bind/host/CIDR metadata so the intended
  access surface is explicit in Nix instead of being hidden in wrappers.
- Host inventory can still opt a specific tape box into a more reachable
  deployment by setting `org.storage.tape.fossilsafe.openFirewall = true` and
  overriding `org.storage.tape.fossilsafe.settings.backend_bind` /
  `allowed_origins` when loopback-only defaults are too strict for the real
  workflow.
- Which host uses `fossilsafe` vs `yatm` now comes from
  [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix) via
  `org.storage.tape.manager`.
- FossilSafe catalog state can now be bootstrapped declaratively from host
  inventory through `org.storage.tape.fossilsafe.bootstrap`, including DB settings,
  OIDC disablement, sources, and schedules.
- Runtime PATH includes the LTFS and tape helpers from this flake, so upstream
  `mkltfs`, `ltfs`, `mt`, `mtx`, `lsscsi`, and `sg3-utils` calls resolve in a
  Nix-friendly way.
- FossilSafe is still upstream alpha software, and its published compatibility
  notes are based on different hardware than this TL2000.
- LTO-4 media is intentionally treated as visible but read-only legacy media by
  default, so it still shows up in scans and can be moved or exported without
  being offered for write/format/wipe workflows.

## Verified Behavior

- Library scan behavior matches the fork docs and backend implementation:
  `fast` scans use `mtx status`, and `deep` scans do `mtx inventory` followed
  by `mtx status`.
- The service now returns a real backend error screen instead of staying on a
  black `Initializing...` overlay if startup checks fail repeatedly.
- Current live status on `desktoptoodle` reports
  `/api/healthz = healthy` and `/api/auth/setup-status = {"setup_required": false, "setup_mode": "relaxed"}`.

## Quick Start

```bash
nix develop ./fruits/fossilsafe
fossilsafe
fossilsafe-bootstrap /path/to/bootstrap.json
fossilsafe-smoke-test
fossilsafe-cli system status
```

For detached iteration against host inventory data:

```bash
nix run ./experiments/fossilsafe -- --flake /work/flake --host desktoptoodle
```

If you want the base tape paths first, check:

```bash
changer-default
tape-default
ltfs-default
```

## Troubleshooting

- If the UI stays on `Initializing...`, check
  `http://127.0.0.1:5001/api/auth/setup-status` directly.
- If that endpoint does not return JSON, first make sure nothing except the
  managed FossilSafe service is already holding the configured backend port.
- A stale hand-started FossilSafe backend can block the service from binding and
  leave the web UI stuck in its startup screen.
