# nix-arbor Flake

An **inventory-driven NixOS flake architecture** for assembling multi-host systems from reusable modules, scoped facts, validation, and generated deployment outputs.

This started as an attempt to organize my NixOS systems around reusable feature branches. It turned into something more useful: a small assembly system where the root flake stays tiny, inventory is the source of truth, reusable modules stay reusable, and the library layer builds the final machines.

The basic idea:

```text
inventory = what exists and what each host wants
dendrites = reusable NixOS behavior
fruits    = named deployable outcomes
homes     = reusable Home Manager behavior
hosts     = machine-specific exceptions
lib       = assembly, validation, dependency resolution, and output generation
```

A host does not need to manually import every piece it depends on.

Instead, a host says:

```text
I am this kind of machine.
I have these users.
I belong to these networks.
I need these capabilities.
Here are my hardware facts.
Here are my deployment hints.
```

Then the flake assembles the final NixOS and Home Manager outputs from that model.

This is not a polished framework. It is a real architecture extracted from my own homelab / workstation setup, cleaned up into a public mirror.

## Why This Exists

A lot of multi-machine NixOS flakes start clean, then slowly collapse into a junk drawer.

At first, the root `flake.nix` is readable. Then you add:

- another host
- Home Manager
- shared users
- roles
- storage
- private networking
- deployment tooling
- host-specific hardware weirdness
- one-off service exceptions

Eventually the root flake starts carrying too much meaning.

This repo tries to avoid that by separating the parts that usually get mixed together.

## The Main Separation

nix-arbor separates four things:

### 1. Facts

Facts are things that are true about the world.

Examples:

- hostnames
- users
- roles
- networks
- ports
- storage devices
- ZFS pool names
- tape device paths
- deployment targets
- bootstrap hints

These live in `inventory/`.

### 2. Behavior

Behavior is reusable NixOS or Home Manager code.

Examples:

- base system setup
- desktop behavior
- ZFS support
- tape support
- private overlay networking
- gaming/workstation setup
- service configuration

These live in `dendrites/`, `homes/`, and `fruits/`.

### 3. Assembly

Assembly is the logic that turns facts plus behavior into final systems.

This lives in `lib/`.

The assembly layer handles things like:

- registry discovery
- inventory normalization
- dependency resolution
- host module assembly
- Home Manager assembly
- validation
- generated deployment outputs

### 4. Overrides

Overrides are the weird machine-specific exceptions that should not pollute reusable modules.

These live in `hosts/`.

A reusable feature should become a dendrite. A weird one-machine fix should become a host override.

## Repository Shape

```text
.
├── flake.nix
├── inventory/
│   ├── hosts.nix
│   ├── users.nix
│   ├── roles.nix
│   ├── networks.nix
│   └── ...
├── lib/
│   ├── assembly.nix
│   ├── registries.nix
│   ├── validation.nix
│   ├── deployments.nix
│   └── ...
├── modules/
│   └── flake-parts/
├── dendrites/
├── fruits/
├── homes/
├── hosts/
├── checks/
└── docs/
```

## Core Concepts

### Inventory

`inventory/` is the source of truth.

It describes what exists, what hosts want, what networks exist, which users exist, which facts are true, and what deployment hints are available.

The point is not to make inventory tiny. The point is to put information where it belongs.

A host can be data-heavy as long as it stays behavior-light.

### Dendrites

`dendrites/` are reusable NixOS capability branches.

They are intentionally close to normal NixOS modules. The difference is that they follow a small convention so they can be discovered, described, selected, validated, and assembled.

Examples:

```text
dendrites/base/
dendrites/desktop/
dendrites/storage/
dendrites/storage/dendrites/zfs/
dendrites/storage/dendrites/tape/
dendrites/network/dendrites/yggdrasil-private/
```

A dendrite should define reusable behavior. It should not need to know every host that may use it.

### Leaves

Leaves are small internal modules owned by a dendrite.

They are implementation details, not global selections.

This keeps a branch organized without making every helper file part of the public assembly surface.

### Fruits

`fruits/` are named deployable outcomes.

A fruit is a service, appliance, persistent app, or higher-level thing that a host can run.

A fruit can require dendrites. For example, a tape-management fruit can require tape-related storage behavior.

### Homes

`homes/` contains reusable Home Manager behavior.

This lets users and roles select Home Manager pieces through inventory instead of wiring everything by hand.

### Hosts

`hosts/` contains host-specific overrides.

This is where machine-specific weirdness goes when it should not become a reusable module.

## What Makes This Useful

### The root flake stays small

The root `flake.nix` is not the brain of the system.

It mainly defines inputs and routes into `flake-parts`.

The actual meaning of the system lives in inventory, reusable behavior, and the library layer.

### Information has controlled scope

The repo tries hard to avoid redundant or misplaced information.

A service module should not need to know every host IP.

A host should not need to manually import every transitive dependency.

Network facts should live with network inventory.

Host facts should live with host inventory.

Reusable behavior should live in reusable modules.

The library stitches the pieces together.

### Adding behavior is straightforward

The usual flow is:

```text
1. add a new dendrite
2. describe it with metadata
3. select it in inventory for the hosts that need it
4. build
```

You do not need to edit the root flake every time you add a new reusable capability.

### The library resolves composition

The library layer can resolve selected dendrites, fruits, required dependencies, users, Home Manager modules, host overrides, and generated outputs.

That means host definitions can stay focused on intent and facts instead of implementation details.

### Validation catches structural mistakes

The flake validates the model before deployment.

Current validation checks include things like:

- unknown users
- unknown roles
- unknown networks
- duplicate ports
- invalid tape managers
- conflicting dendrites
- missing ZFS facts
- missing tape device facts
- missing required fruits
- invalid private overlay network references
- invalid deployment/bootstrap references

This is one of the most important parts of the architecture.

The point is to fail early with a useful error instead of letting mistakes turn into confusing deployment failures.

### Deployment outputs come from the same model

The same inventory can generate:

- `nixosConfigurations`
- `homeConfigurations`
- Colmena output
- deploy-rs output

That keeps deployment metadata close to the host model instead of creating a second hand-maintained source of truth.

## What This Is Good For

This pattern is useful for:

- multi-host NixOS setups
- homelabs
- workstations plus servers
- storage-heavy systems
- private overlay networks
- generated deployment targets
- shared Home Manager setups
- systems with a lot of hardware-specific facts
- configs that need to grow without becoming unreadable

It is especially useful when you want many hosts to share behavior without copying the same information everywhere.

## What This Is Not

This is not a beginner NixOS template.

It is not a polished framework.

It is not a secrets-management solution.

The private repo this came from currently has ugly secret handling because I was focused first on the hardware, tape integration, deployment surfaces, and assembly model. That part needs to be cleaned up properly with a real secrets system.

This public repo is mainly about the architecture.

## Naming Note

This repo still uses the word `dendrites` for reusable capability branches because that language fits the tree model well.

It should not be treated as a strict implementation of any existing public “dendritic NixOS” pattern.

A better description is:

```text
inventory-driven NixOS host assembly
```

or:

```text
a tree-shaped NixOS flake architecture with scoped inventory and reusable behavior branches
```

## Public Mirror Notes

This repository is generated from a private source repo.

That means:

- secrets are removed
- sensitive deployment details are removed or replaced
- some example values are synthetic
- private-only experiments may be omitted
- some rough edges are still visible because this comes from a real working setup

It is currently running on my own hardware across two machines, and I am expanding it further.

## Start Here

Read these first:

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/dendritic-guide.md`](docs/dendritic-guide.md)
- [`docs/authoring-guide.md`](docs/authoring-guide.md)
- [`examples/demo-inventory/README.md`](examples/demo-inventory/README.md)

Quick commands:

```bash
nix flake show
nix flake check
```

## Status

Active, practical, and still evolving.

Some of it is clean. Some of it is experimental. Some of it is there because real machines needed it.

The main value is the structure:

```text
tiny root flake
inventory as source of truth
reusable behavior branches
assembly logic in lib
early validation
generated deployment surfaces
controlled information scope
```

That is the part worth sharing.
