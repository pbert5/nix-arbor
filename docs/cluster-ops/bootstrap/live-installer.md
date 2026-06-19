# Live Installer

This repo now ships a dedicated live installer flow for first contact with new
or reworked machines.

The installer image is a NixOS live environment that is prepared for cluster
bootstrap work:

- `sshd` is enabled
- `root` login is allowed by SSH key only
- every public key under
  [`inventory/keys/leaders/`](/work/flake/inventory/keys/leaders)
  is trusted for `root`
- `nix-command` and `flakes` are enabled
- `git`, `jq`, and `yggdrasil` are already present in the live environment

## What It Is For

Use this when you want a machine to come up in a known-good live environment so
one of the trusted leader systems can take over remotely.

That gives you a repeatable way to reach the target over SSH before the target
has joined the normal Ygg-based management path.

## Important Scope Note

The current live installer solves the "get me a remotely manageable target"
problem.

It does **not** yet fully automate persistent disk installation or partitioning
for every host shape. In the current implementation:

- the live installer gives you remote root access to the booted live system
- `nbootstrap` and `bootstrap-host` can then enroll the host and do the first
  config rollout
- persistent disk install is still an explicit operator step when needed

That boundary is intentional for now, and the docs below call it out clearly so
the operator knows where the live environment ends and where host-specific disk
work begins.

## Main Commands

Build the image:

```bash
nix run .#live-installer
```

Print just the resolved `.iso` path:

```bash
nix run .#live-installer -- --print-image-path
```

Write the image straight to a USB drive:

```bash
nix run .#live-installer-usb -- --device /dev/sdX
```

Use a prebuilt image instead of rebuilding:

```bash
nix run .#live-installer-usb -- --device /dev/sdX --image /path/to/image.iso
```

## What To Do After The Target Boots

1. plug the USB into the target and boot from it
2. make sure the target gets network connectivity
3. determine the target's temporary IP address
4. from a trusted leader, verify SSH reachability:

```bash
ssh -i /path/to/private/key root@TARGET_IP 'hostname && whoami'
```

Expected output:

- the target's hostname or installer hostname
- `root`

5. once SSH works, move into the guided bootstrap flow in
   [`new-host-from-live-installer.md`](/work/flake/docs/cluster-ops/bootstrap/new-host-from-live-installer.md)

## Related Tools

- [`nbootstrap.md`](/work/flake/docs/cluster-ops/bootstrap/nbootstrap.md)
  for the unified operator-facing bootstrap CLI
- [`bootstrap-host.md`](/work/flake/docs/cluster-ops/bootstrap/enrollment/bootstrap-host.md)
  for the lower-level host enrollment tool details
- [`leader-access.md`](/work/flake/docs/cluster-ops/trust/leader-access.md)
  for why the live installer trusts leader keys for `root`
