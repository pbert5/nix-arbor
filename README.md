# Easy Dendritic NixOS Flake

A public, sanitized version of my **dendritic NixOS flake** for building real multi-machine systems without turning `flake.nix` into a giant hand-wired control file.

The basic idea is simple:

- hosts describe what they are
- reusable capability branches describe what they provide
- metadata describes what each branch needs or conflicts with
- the library resolves the final system composition
- validation catches bad combinations early
- deployment surfaces are generated from the same inventory

So instead of every host manually importing every module, the host says something closer to:

> I am this kind of machine.  
> I need these capabilities.  
> I have these facts.  
> I belong to these networks.  
> I expose these services.

Then the flake assembles the actual NixOS and Home Manager outputs.

This is not meant to be a perfect toy template. It is a real architecture extracted from my own homelab / workstation setup, with private details removed.

## Why This Exists

A lot of NixOS flakes start clean and then slowly become a pile of manual imports.

You add one workstation, then a server, then a storage machine, then a weird laptop, then a few shared users, then Home Manager, then deployment tooling, then overlay networking, and suddenly the root flake is where everything goes to die.

I wanted a structure where the repo could keep growing without everything becoming one giant config blob.

This repo is my answer to that problem.

## The Core Shape

The repo is organized around a few main ideas.

```text
inventory/  = what exists
dendrites/  = reusable NixOS capability branches
leaves/     = small internal modules owned by dendrites
fruits/     = named deployable outcomes or services
homes/      = reusable Home Manager branches
hosts/      = machine-specific escape hatches
lib/        = the resolver, validator, and assembly layer
```

The important part is `lib/`.

The folder layout is not the whole trick. The trick is that the flake has an assembly layer that can read inventory, resolve required pieces, validate the combination, and generate the final outputs.

## What Makes It Different

### Tiny root flake

The root `flake.nix` stays intentionally small.

It defines inputs, then routes into `flake-parts` and the module tree. It is not where every host, user, service, and deployment target gets manually wired together.

That means the root stays readable even as the system grows.

### Passive registries

The flake builds registries for:

- `dendrites/`
- `fruits/`
- `homes/`
- `hosts/`

These registries make first-class components discoverable without making every file automatically active.

That distinction matters.

A thing can exist in the tree without being selected by a host. Discovery is not the same thing as activation.

### Dendrites

A dendrite is a reusable capability branch.

Examples might be:

- `base`
- `desktop`
- `storage`
- `storage/zfs`
- `storage/tape`
- `network/yggdrasil-private`
- `system/workstation/gaming`

A host can select dendrites directly. A dendrite can also require other dendrites.

This lets you build systems from capability names instead of repeatedly remembering the full internal module stack.

### Leaves

Leaves are smaller implementation modules inside a dendrite.

They are usually not selected directly by hosts. They are the branch's internal pieces.

This keeps reusable branches organized without turning every tiny file into a global component.

### Fruits

A fruit is a named deployable outcome.

That can be a service, appliance, persistent app, or something that represents an actual thing you want a machine to run.

The distinction is useful:

- dendrite: capability
- leaf: implementation detail
- fruit: deployed outcome

### Metadata-aware composition

Dendrites and fruits have `meta.nix`.

Metadata can describe:

- what a component provides
- what it requires
- what it conflicts with
- what host classes it supports
- what dendrites a fruit needs

The metadata does not replace the real module body. It describes the component so the assembly layer can reason about it.

That is where the "self-assembling" part comes from.

### Validation before deployment

The flake validates the composition instead of letting mistakes show up later as confusing build or deployment failures.

Current validation covers things like:

- unknown users
- unknown roles
- unknown networks
- duplicate ports
- invalid tape managers
- conflicting dendrites
- missing required ZFS facts
- missing required tape device facts
- missing required fruits
- invalid private Yggdrasil peer references
- invalid deployment/bootstrap references

This is one of the parts I care about most. I want the flake to fail early and explain what is structurally wrong.

### Inventory-generated deployment surfaces

The same inventory can generate:

- `nixosConfigurations`
- `homeConfigurations`
- Colmena output
- deploy-rs output

So deployment information does not need to live in a totally separate hand-written config that slowly drifts away from the actual host model.

## Mental Model

This repo is trying to make a NixOS config act less like a pile of files and more like a small system model.

A host definition should mostly answer questions like:

```text
What kind of host is this?
What users exist on it?
What networks is it part of?
What reusable capabilities does it need?
What physical facts does it have?
What services or deployable outcomes should exist?
What host-specific weirdness still needs an override?
```

Then the library turns that into a real machine configuration.

## Example Build Flow

When a host is built, the flow is roughly:

1. `flake.nix` loads the flake-parts modules
2. registries are built from `dendrites/`, `fruits/`, `homes/`, and `hosts/`
3. inventory is normalized
4. selected fruits are resolved
5. required dendrites are added
6. conflicts and missing facts are checked
7. users and Home Manager modules are attached
8. host-specific overrides are applied
9. the final module list is passed to `nixosSystem`

The host does not need to manually know every internal module it depends on.

## What This Is Good For

This pattern is useful if you are managing:

- multiple NixOS machines
- a homelab
- workstations plus servers
- reusable machine roles
- shared Home Manager configs
- private overlay networks
- generated deployment targets
- storage-heavy systems
- weird hardware that still needs clean structure
- systems where facts, policy, and behavior should not all be mixed together

It is especially useful when the config is expected to keep growing.

## What This Is Not

This is not a beginner NixOS starter template.

It is also not a framework that hides Nix from you.

It is a pattern for people who already want a serious multi-machine flake and do not want the root file to become the dumping ground for every decision.

## Public Mirror Notes

This repository is generated from a private source repo.

That means:

- secrets are removed
- sensitive deployment details are removed or replaced
- some example values are synthetic
- private-only experiments may be omitted
- the public repo is meant to show the architecture, not expose my actual infrastructure

Some pieces are polished. Some pieces are experimental. Some pieces exist because real hardware needed them.

The main thing worth sharing is the shape.

```text
small root
structured inventory
passive registries
metadata-described capabilities
library-driven assembly
early validation
generated deployment surfaces
```

## Start Here

Good entry points:

- [`docs/architecture.md`](docs/architecture.md)
- [`docs/dendritic-guide.md`](docs/dendritic-guide.md)
- [`docs/authoring-guide.md`](docs/authoring-guide.md)
- [`inventory/README.md`](inventory/README.md)

Quick commands:

```bash
nix flake show
nix flake check
```

## Status

This is active and practical, not frozen and pristine.

It is built around a real multi-machine setup and then cleaned up for public viewing. The architecture is the main product here: a way to let a NixOS flake grow without losing track of what each piece is supposed to mean.
