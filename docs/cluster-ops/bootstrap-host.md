# Bootstrap Host

`bootstrap-host` is the manual enrollment tool for raw or partially enrolled
machines.

It is currently an alias for the `yggdrasil-bootstrap` package, but the alias
is the name to think in operationally.

## What It Does

Given a host name plus a bootstrap transport path, it:

1. connects to the target over SSH
2. ensures `/var/lib/yggdrasil/keys.json` exists on the target
3. reads the target host's Ygg public key
4. derives the target host's Ygg IPv6 address
5. writes the public identity back into repo inventory
6. updates bootstrap/deployment metadata for that host
7. optionally commits those inventory changes
8. optionally triggers a deployment for the host, and optionally its peers

## What It Edits

- [`inventory/private-yggdrasil-identities.nix`](/work/flake/inventory/private-yggdrasil-identities.nix)
- [`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)

It does not rewrite the hand-authored host definitions in
[`inventory/hosts.nix`](/work/flake/inventory/hosts.nix).

## Most Useful Forms

Dry run using inventory bootstrap metadata:

```bash
nix run .#bootstrap-host -- --host r640-0 --identity-file /home/example/.ssh/bootstrap_key --dry-run
```

Enroll a host and promote future rollout to Ygg:

```bash
nix run .#bootstrap-host -- --host r640-0 --identity-file /home/example/.ssh/bootstrap_key --deployment-transport privateYggdrasil
```

Enroll, commit, and deploy the host:

```bash
nix run .#bootstrap-host -- \
  --host r640-0 \
  --identity-file /home/example/.ssh/bootstrap_key \
  --deployment-transport privateYggdrasil \
  --commit \
  --deploy-tool deploy-rs
```

Enroll, commit, deploy the host, and then roll peers so new trust data spreads:

```bash
nix run .#bootstrap-host -- \
  --host r640-0 \
  --identity-file /home/example/.ssh/bootstrap_key \
  --deployment-transport privateYggdrasil \
  --commit \
  --deploy-tool colmena \
  --deploy-peers
```

## Important Flags

- `--host`
  inventory host name
- `--target`
  raw bootstrap endpoint; optional if `inventory/host-bootstrap.nix` already
  has `targetHost`
- `--identity-file`
  SSH key used to connect during bootstrap
- `--dry-run`
  print what would be discovered without rewriting inventory
- `--deployment-transport privateYggdrasil`
  switch generated deployment targets to prefer the enrolled Ygg address
- `--commit`
  create a Git commit for the inventory edits
- `--deploy-tool deploy-rs|colmena`
  run a first deployment after enrollment
- `--deploy-peers`
  deploy the host's declared Ygg peers too

## What It Does Not Do

- it does not distribute private Ygg keys into the repo
- it does not auto-enable strict peer-source filtering
- it does not silently decide which peers should be rolled out unless you tell
  it to
