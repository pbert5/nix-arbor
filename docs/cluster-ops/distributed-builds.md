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
  sshKey = "/run/keys/REPLACE_ME";
};
```

Builder hosts can publish scheduler hints:

```nix
org.nix.buildMachine = {
  maxJobs = 8;
  speedFactor = 2;
};
```

The `sshKey` path is a local private key path on the coordinator host. The repo
stores the path, not the key material.

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

Check the coordinator can reach the builder with the same private key path:

```bash
ssh -i /home/example/.ssh/bootstrap_key root@200:db8::10 'nix --version'
```
