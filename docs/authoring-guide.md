# Authoring Guide

This guide is for making changes without having to reverse-engineer the whole
assembly flow first.

## Add A Dendrite

Create:

```text
dendrites/<name>/
  <name>.nix
  meta.nix
```

If it grows a real child family, use:

```text
dendrites/<parent>/dendrites/<child>/
  <child>.nix
  meta.nix
```

If that child later grows its own child family, repeat the same pattern:

```text
dendrites/<parent>/dendrites/<child>/<grandchild>/
  <grandchild>.nix
  meta.nix
```

Good pattern:

```nix
{ ... }:
{
  imports = [
    ./leaves/system.nix
    ./leaves/services.nix
  ];
}
```

Use leaves for small focused pieces. Do not build a recursive auto-loader just
because the branch has a few files.

## Add Dendrite Metadata

Use simple descriptive data:

```nix
{
  name = "storage/zfs";
  kind = "sub-dendrite";
  maturity = "stable";
  provides = [ "zfs" ];
  requires = [ "storage" ];
  conflicts = [ ];
  hostClasses = [ "workstation" ];
}
```

Good metadata:

- describes capability
- describes dependencies
- describes conflicts
- stays easy to inspect

Bad metadata:

- hides real behavior
- imports half the repo
- stores secrets

## Add A Fruit

Create:

```text
fruits/<name>/
  <name>.nix
  meta.nix
```

Use a fruit when the thing is a named deployable service or appliance.

Good fit:

- a service
- a containerized workload
- a long-running app

If the thing is just a small internal behavior fragment, it should probably be a
leaf instead.

## Add A Host

Add an entry to `inventory/hosts.nix`.

Start from this shape:

```nix
{
  exported = true;
  system = "x86_64-linux";

  roles = [ ];
  networks = [ ];
  publicYggdrasil = false;
  dendrites = [ ];
  fruits = [ ];
  users = [ ];

  facts = { };
  org = { };

  hardwareModules = [ ];
  overrides = [ ];
}
```

Use:

- `roles` for shared attachment sets
- `networks` for explicit host membership in special network surfaces like
  `privateYggdrasil` or `tailscale`
- `publicYggdrasil` as an explicit per-host opt-in switch; it should stay
  `false` until the repo manages fixed Ygg identities
- `dendrites` for capability branches
- `fruits` for deployable services
- `facts` for machine identity and physical detail
- `org.*` for module-consumed settings such as deployment hints, bootstrap SSH
  access, or service policy
- `hardwareModules` for low-level hardware config imports
- `overrides` for real host-specific exceptions

Bootstrap and rollout metadata that an operator tool may rewrite should usually
live in a dedicated sidecar inventory file rather than the hand-authored host
definitions. This repo uses
[`inventory/host-bootstrap.nix`](/work/flake/inventory/host-bootstrap.nix)
for bootstrap targets, operator-capable markers, deployment tags, and current
deployment transport preference.

## Add A Host Override

Create:

```text
hosts/<name>/
  <name>.nix
```

Then reference it from:

```nix
overrides = [ "<name>" ];
```

Use an override only when the behavior is truly machine-specific. If it is
reusable, move it into a dendrite instead.

## Add A Home Module

Use one of these shapes:

```text
homes/shared/<name>/
  <name>.nix
```

or

```text
homes/<user>/
  <user>.nix
```

Then attach shared home behavior from `inventory/roles.nix` or user-specific
home behavior from `inventory/users.nix`.

## Put Data In The Right Place

Use `facts` for:

- `hostId`
- pool names
- mount roots
- tape device paths

Use `org.*` for:

- linked users
- selected managers
- runtime settings
- policy knobs

That split keeps the inventory readable and helps validation stay honest.

## Add Validation When Needed

If a new branch or fruit has strict requirements, update `lib/validation.nix`.

Examples:

- branch conflicts
- required facts for a selected dendrite
- required fruit for a selected manager
- host-class compatibility

This architecture gets a lot of value from failing early and clearly.

## Document New Features

When you add a new capability, component, flake output, or operator workflow,
update the docs in the same change.

Good default touchpoints are:

- `docs/architecture.md` for repo-level shape changes
- `docs/changes.md` for implemented surface-area changes
- a new focused doc in `docs/` when the feature needs operator guidance or
  design notes
- `README.md` when the new doc should be discoverable from the repo entrypoint

If the change came from a plan document, move the implemented truth into
`docs/` and mark anything still missing as planned work.

## File Naming Rules

- Do not use `default.nix`
- Prefer explicit filenames matching the directory name
- If a file under `modules/` should not be auto-imported, place it under a path
  containing `/_`

## Verification Checklist

After changes:

1. run `git status --short`
2. run `nix flake check`
3. if you added a new file needed by evaluation, stage that file in the correct
   Git repo first
4. update existing docs or add a focused new doc if the change adds a new
  feature, component, or workflow
