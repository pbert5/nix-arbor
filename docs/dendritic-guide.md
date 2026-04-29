# Dendritic Guide

This is the human-readable version of how the flake works now.

## The Big Picture

Think of the repo like a tree:

- `inventory/` says what exists
- `dendrites/` say what kinds of reusable capability can grow
- `fruits/` are named things the tree can actually run
- `hosts/` carry the weird machine-specific exceptions
- `lib/` is the assembly logic that snaps those pieces together

The goal is to keep the root simple and make composition legible.

## What Actually Happens When A Host Is Built

When you build `.#nixosConfigurations.desktoptoodle`:

1. `flake.nix` loads the flake-parts glue in `modules/`
2. the glue builds passive registries from `dendrites/`, `fruits/`, `homes/`,
   and `hosts/`
3. `inventory/hosts.nix` is normalized into the current host schema
4. the resolver figures out which dendrites and fruits the host needs
5. validation checks that the combination makes sense
6. the resolved modules are handed to `nixosSystem`

So the root flake is not doing the detailed work itself. It is routing into the
composition library.

## The Four Most Important Concepts

### Dendrite

A reusable capability branch.

Examples:

- `base`
- `storage`
- `desktop`
- `system`

### Sub-dendrite

A child specialization of a bigger branch.

Examples:

- `storage/zfs`
- `storage/tape`
- `desktop/gnome`

### Leaf

A small internal module imported by a branch.

Examples:

- `dendrites/base/leaves/system.nix`
- `dendrites/base/leaves/services.nix`

Leaves are usually implementation details of a branch, not something a host
selects directly.

### Fruit

A named deployable outcome.

Example:

- `fossilsafe`

Fruits are the things you actually run, expose, or keep alive.

## How The Repo Stays Legible

The repo avoids two common problems:

1. giant root flakes that hand-wire everything
2. unlimited recursive auto-loading where adding a file silently changes
   behavior

Instead, it uses a middle path:

- the root discovers only first-class modules by convention
- each branch owns its own internal imports
- helper code stays inert until explicitly referenced

## Why `meta.nix` Exists

Each dendrite and fruit has metadata so the assembly layer can answer questions
like:

- what does this provide
- what does it require
- what conflicts with it
- what kinds of hosts should use it

Metadata describes a thing. It is not supposed to secretly implement the thing.

## Hosts: Data-Heavy Is Fine

Hosts are not required to be tiny. They are allowed to carry a lot of local
data.

What matters is that the data is separated cleanly:

- `roles`, `dendrites`, `fruits`, `users`
  what the host is selecting
- `networks`
  explicit membership in special inventory-defined networks
- `publicYggdrasil`
  a deliberate host-level switch for future public Ygg exposure, currently kept
  false
- `facts`
  machine-specific facts like pool names, host IDs, and tape device paths
- `org.*`
  settings consumed by modules
- `hardwareModules`
  low-level hardware imports
- `overrides`
  host-specific escape hatches

That is why a machine like `desktoptoodle` can still own a lot of tape-library
detail without collapsing the whole architecture.

## A Real Example

`r640-0` currently works like this:

- role: `workstation`
- dendrite selection includes `storage/zfs`
- facts include the ZFS pool name and mount root
- policy includes linked users under `org.storage.zfs`
- a host override still exists for machine-specific behavior

That split is intentional:

- branch selection says what kind of capability is present
- facts say what hardware or local identity exists
- policy says how that capability should behave

## Validation Is Part Of The Design

This architecture depends on compatibility checks.

The flake already validates things like:

- unknown users or roles
- conflicting dendrites
- missing required ZFS facts
- missing tape devices
- missing FossilSafe fruit attachment for FossilSafe-backed tape setups

If a new branch or fruit has strict requirements, the right answer is usually to
add another validation rule.

## Why `default.nix` Is Banned

This repo wants filenames to explain themselves.

That means:

- `dendrites/storage/storage.nix`
- `hosts/r640-0/r640-0.nix`
- `fruits/fossilsafe/fossilsafe.nix`

not `default.nix` everywhere.

It makes the tree easier to scan and helps the registry conventions stay
obvious.
