# Matrix Hub

Matrix Hub is modeled as the `matrix-hub` fruit and currently selected by
`r640-0` in [`inventory/hosts.nix`](/work/flake/inventory/hosts.nix).
The listen surface is declared in
[`inventory/ports.nix`](/work/flake/inventory/ports.nix) as
`0.0.0.0:6167` on the `tailscale0` interface only, with
`http://r640-0:6167` as the operator-facing URL.

## Runtime

The fruit runs the upstream `services.matrix-continuwuity` NixOS module.
Continuwuity is a single Rust binary (a `conduwuit`/Conduit fork) with an
embedded RocksDB store, so there is no separate Postgres/Redis service to
operate, back up, or upgrade in lockstep.

- systemd unit: `continuwuity.service`
- state directory: `/var/lib/continuwuity/` (systemd `StateDirectory`; not
  overridable per the upstream module — `database_path` is read-only)
- generated config: rendered to a `continuwuity.toml` derivation from
  `services.matrix-continuwuity.settings`, not hand-edited on the host
- package: `pkgs.matrix-continuwuity` (nixpkgs attribute name; upstream
  project name is "Continuwuity", binary is `conduwuit`)

This state directory is not currently wired into any backup plan — see
`inventory/storage/backup-plans/`. Treat the homeserver as disposable/private
until that's addressed.

## Configuration

The fruit hardcodes a private posture in
[`fruits/matrix-hub/matrix-hub.nix`](/work/flake/fruits/matrix-hub/matrix-hub.nix):

- `allow_federation = false` — this homeserver does not talk to the public
  Matrix network; no `.well-known` delegation or 8448 federation listener is
  needed or opened
- `allow_registration = false` — no self-service signup; see bootstrap flow
  below for creating the first account
- `address = [ "0.0.0.0" ]` with the actual restriction enforced at the
  firewall (`networking.firewall.interfaces.tailscale0.allowedTCPPorts`), the
  same pattern used by the `hydrui` fruit — not exposed on the public LAN or
  over Yggdrasil

`server_name` defaults to `matrix.internal` and can be overridden per host via:

```nix
org.matrixHub.serverName = "matrix.internal";
```

Since federation is disabled, `server_name` only shapes user/room IDs and does
not need to resolve publicly.

## Bootstrapping The First Account

Admin bootstrap is automated. The `matrix-hub-bootstrap.service` oneshot unit
runs after `continuwuity.service` on first boot (guarded by
`/var/lib/matrix-hub-bootstrap/done`). It:

1. Waits for the HTTP endpoint to respond (up to 60 s).
2. Extracts Continuwuity's one-time registration token from the unit journal.
3. Registers an `@admin:matrix.internal` account via the Matrix UIAA API using
   that token.
4. Saves a randomly-generated password to
   `/var/lib/matrix-hub-bootstrap/admin-password` (root:root 600) and marks
   bootstrap done.

To retrieve the password from a Tailscale-connected machine:

```bash
ssh r640-0 cat /var/lib/matrix-hub-bootstrap/admin-password
```

The first account is automatically promoted to admin by Continuwuity, so this
credential can be used immediately to log in and manage the server via the
admin management room in any Matrix client.

If bootstrap did not run (e.g. the service was added after the first deploy),
force a re-run:

```bash
ssh r640-0 'rm /var/lib/matrix-hub-bootstrap/done && systemctl start matrix-hub-bootstrap'
```

## Verifying The Service

From a Tailscale-joined machine:

```bash
curl http://r640-0:6167/_matrix/client/versions
systemctl status continuwuity   # on r640-0
journalctl -u continuwuity -f   # on r640-0
```

A working server returns a JSON `versions` list from the `curl` call.

## Planned, Not Yet Implemented

[`plans/matrix_ideas.md`](/work/flake/plans/matrix_ideas.md) sketches a
fuller rollout: a `comm/matrix-bot` dendrite for an ops bot, a
`comm/matrix-alerts` dendrite for systemd/deploy/ZFS event notifications, and
per-room inventory data. None of that exists yet — this fruit is homeserver
only. Add those dendrites under `dendrites/comm/` when bot/alert work starts.
