# Architecture

This repo now uses a dendritic flake shape centered on passive registries and
data-driven assembly.

## Short Version

- `flake.nix` is intentionally tiny and only routes into `flake-parts`
- `modules/flake-parts/` is glue
- `lib/` owns normalization, registry discovery, assembly, and validation
- `inventory/` is the data model for hosts, users, roles, networks, and related
  site data
- `dendrites/` holds reusable NixOS capability branches
- `homes/` holds reusable Home Manager branches
- `fruits/` holds deployable long-running outcomes
- `hosts/` holds host-specific override modules

The flake is assembled from names in inventory, not from a root file that
manually lists every host and module.

## Current Assembly Flow

1. `flake.nix` calls `flake-parts` with `import-tree ./modules`
2. `modules/flake-parts/registries.nix` publishes passive registries for:
   - `dendrites/`
   - `fruits/`
   - `homes/`
   - `hosts/`
3. `modules/flake-parts/configurations.nix` imports `inventory/inventory.nix`
4. `lib/inventory.nix` normalizes host and user data
5. `lib/validation.nix` validates inventory and host composition
6. `lib/assembly.nix` turns the normalized inventory into:
   - `flake.nixosConfigurations`
   - `flake.homeConfigurations`
7. `modules/flake-parts/deployments.nix` turns that same inventory plus the
  built NixOS configurations into:
  - `flake.colmena`
  - `flake.colmenaHive`
  - `flake.deploy`

## Directory Roles

- `inventory/`
  Declarative data. Hosts, users, roles, networks, storage, ports, and similar
  facts.
- `lib/`
  Inert helpers. Registry discovery, assembly, normalization, endpoints,
  validation, and user-module publishing.
- `modules/flake-parts/`
  Root glue only. Outputs, registries, checks, and flake-parts wiring.
- `dendrites/`
  Reusable capability branches such as `base`, `desktop`, `media`, `storage`,
  and `system`.
- `fruits/`
  Named deployable outcomes such as `fossilsafe`.
- `homes/`
  Shared Home Manager branches plus per-user home entrypoints.
- `hosts/`
  Host-specific override modules such as `hosts/r640-0/r640-0.nix`.
- `checks/`
  Repository checks such as `checks/no-default-nix.nix`.
- `experiments/`
  Prototype and unstable work that should stay outside the primary flake.

## Dendrite Model

The repo currently uses explicit nested dendrite discovery:

- top-level dendrites live at `dendrites/<name>/<name>.nix`
- child dendrites live under branch-owned directories such as
  `dendrites/<parent>/dendrites/<child>/<child>.nix`
- deeper child families can keep growing beneath a discovered child branch, for
  example `dendrites/system/dendrites/workstation/gaming/gaming.nix`
- dendrite entrypoints import their own leaves explicitly
- helper files are inert until referenced

Examples:

- `dendrites/base/base.nix`
- `dendrites/desktop/dendrites/gnome/gnome.nix`
- `dendrites/system/dendrites/workstation/gaming/gaming.nix`
- `dendrites/storage/dendrites/zfs/zfs.nix`

This keeps registry discovery convention-based while still allowing a branch to
grow deeper specializations without making helper files active by accident.

## Leaves, Fruits, And Metadata

- A leaf is a small focused behavior module imported by a branch entrypoint.
- A fruit is a deployable persistent outcome that may depend on dendrites.
- Dendrites and fruits currently require `meta.nix`.

Metadata is used for:

- capability description
- dependency resolution
- conflict checks
- host-class validation
- documentation and future introspection

Metadata does not replace the actual module body.

## Host Model

Hosts are allowed to be data-heavy, but they should stay behavior-light.

The current host schema separates:

- identity: `exported`, `system`
- selection: `roles`, `networks`, `dendrites`, `fruits`, `users`
- network risk posture: `publicYggdrasil`
- machine facts: `facts.*`
- consumed policy: `org.*`
- hardware imports: `hardwareModules`
- host escape hatches: `overrides`

Examples in the current inventory:

- `r640-0` selects `storage/zfs` and provides `facts.storage.zfs.*`
- `desktoptoodle` selects `system/workstation/gaming` for Steam, selects
  `storage/tape`, attaches the `fossilsafe` fruit, and carries tape device
  facts plus `org.storage.tape.*` settings

## Validation

The active flake already validates several architectural rules:

- no unknown users or roles in inventory
- no duplicate claimed ports
- no invalid tape managers
- no conflicting dendrites in a resolved host composition
- required facts for `storage/zfs`
- required tape devices for `storage/tape`
- required fruit attachment for FossilSafe-backed tape setups
- private Yggdrasil nodes and peer references in `inventory/networks.nix`
- explicit network-to-dendrite declarations in `inventory/networks.nix`
- exported deployment targets for generated Colmena and deploy-rs surfaces

## Network And Deployment Surfaces

The repo now also assembles a private overlay and deploy surfaces from the same
inventory:

- `inventory/networks.nix` defines the private Yggdrasil topology
- hosts opt into named networks through `inventory/hosts.nix`
- `network/yggdrasil-private` materializes Yggdrasil settings, overlay aliases,
  and firewall policy from inventory
- `network/tailscale` is attached through explicit host network membership on
  hosts that need cross-network bridge reachability
- `lib/deployments.nix` generates Colmena and deploy-rs targets from exported
  hosts plus deployment hints in `org.deployment`

For operator-facing details, see
[`docs/private-overlay-and-deployments.md`](/work/flake/docs/private-overlay-and-deployments.md).

## Current Drift From Earlier Plans

Some older docs still described the previous `modules/dendrites`,
`modules/home`, and `modules/hosts` architecture. That is no longer the active
shape.

The future direction of exposing more composition directly from root `flake.nix`
may still be interesting, but the code today is truthfully:

- tiny `flake.nix`
- `flake-parts` glue under `modules/`
- passive registries from `dendrites/`, `fruits/`, `homes/`, and `hosts/`

For a plainer walkthrough, see
[`docs/dendritic-guide.md`](/work/flake/docs/dendritic-guide.md). For
authoring steps, see
[`docs/authoring-guide.md`](/work/flake/docs/authoring-guide.md).
