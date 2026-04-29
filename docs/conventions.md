# Conventions

## Core Rules

- Keep `flake.nix` tiny.
- Keep real assembly in `modules/flake-parts/` plus `lib/`.
- Keep `inventory/` data-first.
- Keep `lib/` inert and helper-focused.
- Keep reusable NixOS behavior in `dendrites/`.
- Keep reusable Home Manager behavior in `homes/`.
- Keep deployable outcomes in `fruits/`.
- Keep host-specific quirks in `hosts/`.
- Keep unstable work in `experiments/`.

## Naming Rules

- `default.nix` is forbidden in active repo-owned paths.
- Prefer explicit filenames that match the directory name:
  - `dendrites/storage/storage.nix`
  - `dendrites/storage/dendrites/zfs/zfs.nix`
  - `fruits/fossilsafe/fossilsafe.nix`
  - `hosts/r640-0/r640-0.nix`
- Redundant names are acceptable when they make the tree easier to scan.

## Dendrite Rules

- Root registry discovery should stay limited to top-level dendrites plus one
  child level.
- Dendrite entrypoints should usually import their own leaves explicitly.
- Do not build unlimited recursive auto-loading inside branches.
- Use a child dendrite only when a branch grows a real specialization family.
- Do not auto-import helper code from `lib/`.

## Metadata Rules

- Dendrites and fruits require `meta.nix`.
- Metadata should describe a thing, not do the thing.
- Use metadata for:
  - capabilities
  - requirements
  - conflicts
  - host-class validation
  - maturity and runtime description
- Do not put real module bodies, secrets, or hidden dynamic imports in metadata.

## Host Rules

- Hosts may be data-heavy, but they should stay behavior-light.
- Put machine facts in `facts`.
- Put consumed policy in `org.*`.
- Put hardware imports in `hardwareModules`.
- Put machine-specific escape hatches in `overrides`.
- Prefer explicit child branch selection such as both `storage` and
  `storage/zfs` when it improves readability, even if metadata can resolve the
  requirement.

## Inventory Rules

- `inventory/hosts.nix` is for host descriptions.
- `inventory/users.nix` is for reusable user identity and per-user facts.
- `inventory/roles.nix` is for shared attachment sets.
- Keep low-risk inventory data declarative and centralized.
- Do not scatter host facts into reusable dendrites unless the fact is actually
  shared.

## Auto-Import Rules

- Only `modules/` is auto-imported through `import-tree`.
- If a file under `modules/` should not be auto-imported, place it under a path
  containing `/_`.
- Helper/support files outside `modules/` are fine as long as they are only
  imported explicitly.

## Validation Rules

- Add assertions early when a branch or fruit has compatibility requirements.
- Prefer a clear evaluation failure to a silently wrong composition.
- Keep architectural checks in Nix when practical.

## Docs Rules

- When architecture changes, update the skills and repo docs together.
- Document current implementation truthfully.
- If design notes describe future work, label them as planned or remaining
  drift rather than present fact.
- When a change adds a new feature, component, flake output, or operator
  workflow, update the relevant docs in the same change.
- Prefer a focused new doc when the feature needs usage guidance, and then link
  to it from broader overview docs.
