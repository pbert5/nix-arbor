# Nix Arbor

Nix Arbor is a small, modern Nix integration flake: an explicit composition
layer for independently versioned flakes.

It is not the permanent home of every package, module, machine identity,
service, secret, or cluster record. Those belong in focused child repositories
when they become real.

## Start here

```sh
nix develop
```

The default development shell is powered by AshZsh. It activates an isolated
Home Manager generation under `/tmp/nix-arbor-ashzsh` and starts AshZsh's Zsh
for interactive sessions. The generation is cached by activation-package
identity and does not modify the normal home configuration or start user
services.

Or enable automatic loading once in this checkout:

```sh
direnv allow
```

Automatic loading requires `direnv` and `nix-direnv` to already be installed
and enabled for your shell; the dev shell supplies them for subsequent work.

`.envrc` delegates to nix-direnv's `use flake`. Direnv is convenience; the
declarative environment remains `devShells.default` in the flake. Navi is
available inside the shell and automatically searches this project's `cheats/`
first. `nix run .#help` provides the same project-local Navi entry point.

## Discovery and maintenance

```sh
nix flake show
nix flake metadata
nix flake check
nix fmt
navi
```

The Navi cheats are an annotated learning/reference system, not just aliases.
They cover Nix language and CLI fundamentals, flakes and locks, development
shells, store and profile operations, debugging, NixOS builds/VMs/tests/
containers, and local child-flake overrides. Use `navi --print` to review a
command before executing it.

For local component development with Git submodules and `--override-input`, see
[DEV.md](DEV.md).

## Layout

```text
flake.nix          small input and flake-parts composition entry point
modules/           root composition modules for shell, checks, and apps
cheats/            project-local Navi learning/reference cheats
docs/              architecture decisions and future composition workflow
packages/          active and future independently versioned child flakes
src/               reserved for source genuinely belonging to Nix Arbor
tests/             reserved for future focused tests; none required yet
.envrc             nix-direnv automatic shell activation
Justfile           thin discoverability recipes around native Nix commands
```

Only directories with current files are committed; `packages/`, `src/`, and
`tests/` are conventions, not empty placeholders.

## External component development

Nix Arbor declares real child flakes as remote inputs. AshZsh is the first
examples:

```nix
inputs.ashzsh.url = "github:pbert5/AshZsh";
inputs.ashes-desktop-apps.url = "github:pbert5/AshDesktopApps";
```

The remote input is the reproducible default. A local Git checkout is kept
under `packages/AshZsh` as a Git submodule for convenient joint development.
The submodule is not itself the flake input; it is the working tree used by a
temporary override:

```sh
nix flake check --override-input ashzsh path:./packages/AshZsh
nix develop --override-input ashzsh path:./packages/AshZsh
nix build .#some-output --override-input ashzsh path:./packages/AshZsh
```

Edit AshZsh in `packages/AshZsh`, check the child directly with `nix flake
check` from that directory, then check Nix Arbor against the local child with
the commands above. The override is temporary and does not change the
committed lock file.

There are three independently versioned records:

1. AshZsh's Git repository HEAD.
2. Nix Arbor's Git submodule pointer to a specific AshZsh commit.
3. Nix Arbor's `flake.lock` entry for the remote `ashzsh` input.

After validating a child change, update the submodule pointer from the Nix
Arbor root:

```sh
git -C packages/AshZsh fetch
git -C packages/AshZsh checkout <validated-ashzsh-commit>
git add packages/AshZsh
git commit -m "chore: update AshZsh submodule"
```

Separately update the reproducible remote input when desired:

```sh
nix flake lock --update-input ashzsh
git add flake.lock
git commit -m "chore: update AshZsh flake input"
```

Updating one does not automatically update the other. The local override is
what lets active AshZsh work proceed before either record is changed.

## Updating and learning

Update all inputs with `nix flake update`, or one input with
`nix flake lock --update-input nixpkgs`. Prefer the targeted form when a change
does not require refreshing the whole graph.

`just` offers thin aliases for discovery, checking, formatting, linting, shell,
REPL, metadata, and output inspection; the native Nix command remains visible.
The repository's formatter is `nixfmt` driven through `nixfmt-tree`, and
`nix flake check` runs formatting, statix, and deadnix checks immediately.

This phase deliberately excludes hosts, hardware, deployments, secrets, cluster
topology, and applications; reusable child flakes live in their own repositories.

## Ashes Tools package sets

Ashes Tools is a separately versioned package-set library consumed remotely by
this flake. Its `lib.sets` functions accept Arbor's `pkgs`, while its package
and devShell outputs provide convenient imperative use:

```sh
nix flake show github:pbert5/AshesTools
nix profile add github:pbert5/AshesTools#nix-dev
nix shell github:pbert5/AshesTools#network
nix develop github:pbert5/AshesTools#nix-dev
```

The Arbor dev shell uses `inputs.ashes-tools.lib.sets.nix-workstation pkgs` for
reusable package selection; AshZsh activation and Arbor-specific Navi behavior
remain local to Arbor.

Ash Desktop Apps is the desktop/GUI counterpart. Its canonical sets are
consumed independently, for example:

```sh
nix profile add github:pbert5/AshDesktopApps#desktop-coding
nix shell github:pbert5/AshDesktopApps#desktop-core
```

Local Nix Arbor development uses the same temporary substitution convention:

```sh
nix flake check --override-input ashes-desktop-apps path:./packages/AshDesktopApps
```

## Desktop demo VM

The [TilingDesktop](https://github.com/pbert5/TilingDesktop) component includes
a generic VM for testing the tuigreet, Hyprland, and Niri desktop stack:

```sh
nix run github:pbert5/TilingDesktop#demo-vm
```

From a local component checkout:

```sh
cd packages/tiling-desktop
nix run .#demo-vm
```

Log in with user `demo` and password `demo`, then use tuigreet to select
Hyprland or Niri. See the child component README for build and configuration
details.

## Agent-first development

Use one branch and one sibling worktree per agent task. The helper, role briefs,
Codex/Claude configuration, VS Code tasks, and handoff guidance are described
in [docs/agent-workflows.md](docs/agent-workflows.md). Repository-local MCP
configuration and toggles are documented in
[docs/codex-development.md](docs/codex-development.md). Run
`git submodule update --init` when a checkout needs Nix Arbor's direct child or
reference repositories. Use recursive mode inside a child only when that child
has a valid `.gitmodules` file.

`references/flake-devbox` is a legacy/reference submodule for inspection. It is
not a Nix Arbor flake input and should not be casually modified or ported
wholesale. Active independently versioned components belong under `packages/`
and retain their own repository workflows.

## Machine inventory

Static machine facts live under `config/machines/`. Each directory is named
after its machine and contains a concise `default.nix` descriptor. Optional
`hardware-configuration.nix` and `configuration.nix` files are automatically
included by Arbor Manager.

Use the ordinary NixOS outputs with `nix flake show`, or evaluate and build:

```sh
nix eval .#nixosConfigurations.desktoptoodle.config.networking.hostName
nix build .#nixosConfigurations.desktoptoodle.config.system.build.toplevel
nix build .#nixosConfigurations.r640-0.config.system.build.toplevel
```

Deployment remains standard NixOS tooling; switching is an operator action:

```sh
nixos-rebuild build --flake .#desktoptoodle
nixos-rebuild switch --flake .#desktoptoodle --target-host <host>
```

Add a machine by creating its directory, descriptor, and normal generated
hardware module. On the target, `nixos-generate-config --show-hardware-config`
provides the hardware module; review and save it as
`config/machines/<name>/hardware-configuration.nix`.

Committed inventory contains stable Git/Nix build facts: architecture,
hostname, profile, boot/storage facts, and static module choices. Future live
registry facts such as health, presence, membership, and changing topology
will enter through another machine source rather than being committed here.

The initial profiles are `desktop` and `server`. desktoptoodle consumes
TilingDesktop, AshZsh, and Ash Desktop Apps; r640-0 uses the conservative SSH
server profile. Legacy cluster state, dynamic enrollment, large media/storage
services, NVIDIA tuning, and user-specific application lists are intentionally
omitted.

## Arbor Registry boundary

The standalone `packages/arbor-registry` component owns pure signed-record
validation, accepted/materialized projections, quarantine, relationship graph
queries, endpoint/service metadata, and declarative public policy options. The
root flake consumes the independent `github:pbert5/arbor-registry` input; use
`nix run .#local -- overrides` to inspect local development overrides.

Nix evaluation consumes immutable snapshots and never queries a live registry.
Nix/Git contains construction logic, Arbor Registry contains mutable public
cluster knowledge, OpenBao owns privileged runtime authority and secret values,
and Arbor Manager creates inspectable source/selection/deployment plans. The
optional transport has an executable two-daemon convergence test, and the
runtime provider has an executable OpenBao dev-server delivery test. Signed
enrollment, identity-generation/revocation, recovery approvals, initial
credential gating, and resumable deployment receipts are now runtime
boundaries. A real NixOS VM now validates upstream systemd-vaultd socket delivery;
real SSH/Colmena host execution remains an external integration. See [the architecture](docs/arbor-registry-architecture.md) and
[the migration matrix](docs/arbor-registry-migration-matrix.md).
