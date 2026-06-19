# Agent Working Agreement

This repository prefers declarative Nix workflows.

## Core Direction

- Default to declarative configuration over ad-hoc imperative scripts.
- Keep system behavior encoded in Nix whenever practical.
- Favor small, composable modules with clear ownership.
- Beyond the core host age encryption key installed during enrollment, manage
  machine setup and cluster behavior declaratively through the flake. Use the
  live USB installer and NixOS modules for initial setup whenever practical.

## Documentation Hygiene

- When adding or changing a feature, component, flake output, inventory surface,
  or operational workflow, update the relevant docs in the same change.
- Prefer updating existing docs when they already cover the area, and add a new
  focused doc when the feature needs usage notes, architecture notes, or
  operator guidance of its own.
- Do not leave implemented behavior documented only in plans, chat history, or
  code comments; promote current truth into `docs/`.
- When a plan document becomes partially implemented, document the implemented
  subset clearly and label remaining items as planned rather than present fact.

## Agent Skill Usage

- For Nix, NixOS, Home Manager, flakes, overlays, derivations, dev shells, or
  repo-layout work, invoke the `nixos` skill (`$nixos` in Codex, `/nixos` in
  Claude).
- For flake architecture, module-boundary decisions, cross-class composition, or
  the preferred design theory for the primary system flake and `experiments/`,
  invoke the `dendritic` skill (`$dendritic` in Codex, `/dendritic` in Claude)
  as an appendix to the `nixos` skill.
- Both skills are authored under `.github/skills/` and exposed through
  `.agents/skills/` for Codex and `.claude/skills/` for Claude.
- Load only the reference files needed for the current task from
  `.github/skills/nixos/references/` to keep context focused.
- Keep the discoverable skill under `.github/skills/nixos/` aligned with the
  source material under `skills/third-party/kettleofketchup-nixos/` when it is
  updated.
- Prefer the `dendritic` skill's aspect-oriented design theory when shaping the
  main flake or experiment-local flakes: thin entry points, feature-first
  modules, and composition across NixOS/Home Manager/Darwin where it helps.

## Inventory and Lib Boundaries

- `inventory/` is **data only**. Files there must not contain assembly code:
  no derivations across multiple sources, no `builtins.readFile` for keys, no
  dynamic URL construction, no filtering/mapping that joins inventory files.
- Assembly logic belongs in `lib/`. The entry point for all inventory-level
  derivations is `lib/inventory.nix`'s `normalizeInventory`, which is called
  once by the flake and receives the entire raw inventory.
- Extend `lib/inventory.nix` (or add a focused helper under `lib/`) for new
  derivations, then wire them into `normalizeInventory`.
- Typical things that belong in lib, not inventory:
  - Deriving leaders/remotes from host roles and network data
  - Merging identity service records (e.g. yggdrasil addresses) into network
    node definitions
  - Reading and normalizing key files
  - Any cross-file join or transformation

## File Naming

- Never use `default.nix`.
- Prefer explicit filenames even when the filename repeats the parent directory
  name.
- Redundant names are acceptable if they make the tree easier to visually
  interpret.

## Auto-Import Hygiene

- This repo uses `import-tree` to auto-import active modules under `modules/`.
- If a file under `modules/` should not be auto-imported, place it under a path
  containing `/_`.

## Container Policy

- Podman is the backend of record.
- Prefer Nix-native container management (`virtualisation.oci-containers`)
  instead of compose-style orchestration.
- Avoid introducing Docker Compose or non-declarative container wrappers unless
  explicitly requested.
- We can skip `virtualisation.oci-containers` for programs that are one-shot
  runs.

## Experiment Isolation (Important)

- Unstable/prototype work must stay isolated under `experiments/`.
- For experiments, changes should live in the experiment flake and
  experiment-local files, not in the system flake by default.
- Do not wire experimental services/modules into `flake.nix`, host assemblies,
  or shared system roles until the experiment is declared stable.
- Promotion from `experiments/` to system-level modules should be an explicit,
  separate step.

## Flake Evaluation Hygiene

- Flakes ignore untracked files.
- Before evaluating, building, or rebuilding a flake change that depends on a
  newly created file, stage the required untracked files first.
- Stage them in the correct Git repo for the flake being evaluated.
- If nested Git repos exist, determine which repo owns the file instead of
  blindly staging from the current directory.
- Do not stage unrelated files just to make evaluation pass.

## Live Cluster Validation

- Leader hosts such as `desktoptoodle` and `r640-0` have root SSH access to
  all devices defined in the flake. When working from one of those leaders,
  you may use `clusterctl deploy` for the host or hosts currently being
  changed.
- When validating changes intended for the live cluster, deploy to each managed
  machine with `clusterctl deploy r640-0 desktoptoodle t320-0` unless the user
  explicitly asks for a dry run or a narrower host set.
- Long-running deploys can burn excessive agent tokens while producing little
  useful signal. After starting a deploy that is expected to run for a while,
  do not keep polling it to completion by default; report that it is running
  and let the user reprompt when it finishes or needs attention.
