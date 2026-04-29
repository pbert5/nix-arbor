# Command Reference

This page explains the commands we have been using and what each one actually
means.

## Raw SSH Check

```bash
ssh -i /home/example/.ssh/bootstrap_key root@r640-0 'hostname && whoami'
```

Use this to verify that a bootstrap or leader deployer key can reach the target
as `root`.

What it proves:

- root SSH access works
- the host is reachable over the current management path
- the key in use is accepted by the target

Expected output shape:

- host name, such as `r640-0`
- user name, such as `root`

## Ygg Identity Dry Run

```bash
nix run .#yggdrasil-bootstrap -- --host r640-0 --target 100.64.0.10 --identity-file /home/example/.ssh/bootstrap_key --dry-run
```

This connects to the target, ensures the Ygg key file exists, reads the public
key and derived Ygg address, and prints them without rewriting inventory.

Use it when:

- you want to verify SSH/bootstrap reachability
- you want to see what identity the host will publish
- you are debugging before making repo changes

## Bootstrap Host Dry Run

```bash
nix run .#bootstrap-host -- --host r640-0 --identity-file /home/example/.ssh/bootstrap_key --dry-run
```

This is the same bootstrap tool under a more operator-oriented name.

What is special here:

- it can omit `--target` if `inventory/host-bootstrap.nix` already has a
  `targetHost`
- it prints both the resolved bootstrap connection metadata and the discovered
  Ygg identity

For `r640-0`, the dry run currently resolves:

- bootstrap target: `100.64.0.10`
- ssh user: `root`

## Real Bootstrap Enrollment

```bash
nix run .#bootstrap-host -- --host r640-0 --identity-file /home/example/.ssh/bootstrap_key --deployment-transport privateYggdrasil
```

This updates:

- [`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
- [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)

It does not automatically force peer firewall lockdown.

## Show The Generated deploy-rs Target

```bash
nix eval '.#deploy.nodes.r640-0' --json
```

Use this to inspect what deploy-rs thinks the host should be called and how it
will connect.

This is the easiest way to confirm that a host has switched from bootstrap IP
transport to Ygg transport.

## Run The Pinned Deployment Tools

```bash
nix run .#deploy-rs -- .#r640-0
nix run .#deploy-rs -- .#desktoptoodle
nix run .#colmena -- apply --on r640-0
```

These use the flake-pinned tool versions instead of whatever happens to be in
your shell environment.
