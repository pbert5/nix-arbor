# Distributed Builds

The repo models Nix distributed builds as an opt-in system dendrite:
`system/distributed-builds`.

## What It Does

On each enrolled coordinator host, the dendrite sets:

```nix
nix.distributedBuilds = true;
nix.settings.builders-use-substitutes = true;
nix.buildMachines = [ ... ];
```

The build machine list is generated from inventory rather than handwritten per
host.

## Inventory Shape

Coordinator hosts select the dendrite and name their builders:

```nix
dendrites = [
  "system/distributed-builds"
];

org.nix.distributedBuilds = {
  builders = [ "r640-0" ];
};
```

Builder hosts can publish scheduler hints:

```nix
org.nix.buildMachine = {
  maxJobs = 8;
  speedFactor = 2;
};
```

On leader coordinators, the dendrite prefers the SOPS-installed
`cluster-identity-leader-user-ssh-nix-build` key. That copy is root-readable
for the Nix daemon's SSH client, while the normal operator key remains in the
leader user's `~/.ssh`.

If that key is unavailable, the coordinator reuses the local key path already
resolved for its cluster registry transport/signing identity, then falls back to
the coordinator's `inventory/host-bootstrap.nix` `identityFile`.
`org.nix.distributedBuilds.sshKey` and `builderOverrides.<name>.sshKey` remain
explicit local-path overrides; those paths must be readable by the Nix daemon's
remote build hook. The repo stores paths, not private key material.

## Transport Resolution

Builder hostnames are resolved from inventory in the same spirit as generated
deployment targets:

1. enrolled private Ygg address when the builder's deployment transport is
   `privateYggdrasil`
2. bootstrap `targetHost`
3. private Ygg endpoint fallback
4. host inventory name

## Current Enrollment

Current distributed-build clients/builders:

- `desktoptoodle` builds on `r640-0`
- `r640-0` builds on `desktoptoodle`

## Sanity Checks

Inspect generated build machines:

```bash
nix eval '.#nixosConfigurations.desktoptoodle.config.nix.buildMachines' --json
```

Check the coordinator can reach the builder with its resolved identity:

```bash
ssh r640-0 'nix --version'
```

Force a tiny remote build through the same Nix hook:

```bash
nix build --impure --no-link --max-jobs 0 \
  --expr 'with import <nixpkgs> {}; runCommand "remote-builder-smoke" {} "echo ok > $out"'
```
