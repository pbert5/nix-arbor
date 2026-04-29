# Troubleshooting

This page collects the most common operator-facing failure modes.

## `bootstrap-host --dry-run` Cannot Reach The Host

Check:

- `targetHost` in `inventory/host-bootstrap.nix`
- `sshUser` in `inventory/host-bootstrap.nix`
- the SSH identity file you passed
- whether the leader key is already present on the target

Start with:

```bash
ssh -i /path/to/key root@target 'hostname && whoami'
```

## A Leader Still Cannot SSH Into Another Host

Check both halves of the trust path:

- the target host trusts the leader public key
- the leader actually has the matching private key locally

This repo only distributes the public half through
[`inventory/keys/leaders/`](/work/flake/inventory/keys/leaders).

Typical symptom:

- the public key exists in inventory
- the target is rebuilt
- SSH still fails with `Permission denied (publickey,...)`

That usually means the leader never had the matching private key, or it rotated
to a new key and the repo still trusts the old public one.

## `deploy-rs` Still Uses The Bootstrap IP

Check:

- `deploymentTransport = "privateYggdrasil"` in `inventory/host-bootstrap.nix`
- the host has an enrolled Ygg address in
  `inventory/private-yggdrasil-identities.nix`

Inspect with:

```bash
nix eval '.#deploy.nodes.r640-0' --json
```

## `deploy-rs` Prompts For A Root Password

Check whether the generated deploy target includes the expected identity file:

```bash
nix eval '.#deploy.nodes.r640-0.sshOpts' --json
```

Then test the same key directly:

```bash
ssh -i /home/example/.ssh/bootstrap_key root@200:db8::10 'hostname && whoami'
```

If direct SSH succeeds but deploy-rs prompts for a password, the deploy target
is not passing the identity file. Set `identityFile` for that host in
[`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix).

## `deploy-rs` Prints Unknown Flake Output Warnings

Warnings like these are currently expected with this flake shape when a tool
runs `nix flake check` internally:

- `unknown flake output 'colmena'`
- `unknown flake output 'colmenaHive'`
- `unknown flake output 'deploy'`
- `unknown flake output 'inventory'`
- `unknown flake output 'dendritic'`

Those outputs are repo-specific convenience surfaces, not standard flake output
classes. They are safe to ignore as long as deploy-rs continues past the check
phase and evaluates the requested node.

## `system.stateVersion` Defaulting Warnings In Evaluation

Real exported hosts get `system.stateVersion` from the base system dendrite.
Synthetic NixOS checks should set their own explicit value too; if this warning
appears again, look for a small test-only `nixosSystem`, `evalConfig`, or NixOS
VM test that bypasses the normal host assembly path.

## Download Buffer Warnings

The base system dendrite sets `nix.settings.download-buffer-size` higher than
the Nix default to avoid transient large-download warnings during deploy checks
and builds. If this warning appears on a leader machine, switch that leader to
the current config so the local Nix daemon picks up the setting.

## App `meta.description` Warnings

If you see these, the app wrapper is missing metadata. The repo now sets
descriptions for the operator apps in
[`modules/flake-parts/outputs.nix`](/work/flake/modules/flake-parts/outputs.nix).
