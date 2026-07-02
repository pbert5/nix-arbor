# Inventory Instructions

Apply these rules to site data under `inventory/`.

- `inventory/` is data only.
- Inventory files must not contain assembly code: no derivations across
  multiple sources, no `builtins.readFile` for keys, no dynamic URL
  construction, and no filtering or mapping that joins inventory files.
- All service/listener ports used by the flake belong in `inventory/ports.nix`,
  including localhost-only, private overlay-only, experimental, and reserved
  ports.
- Prefer the normalized host shape in `inventory/hosts.nix`: branch selection in
  `dendrites` and `fruits`, machine facts in `facts`, and consumed policy in
  `org.*`.
- Subdirectories carry data too: `identity-services/` stores per-service
  identity records, `keys/` stores host age recipients and leader signing keys,
  and `storage/` stores storage inventory.
- Cross-file joins, derived leaders/remotes, key-file reading, and network node
  merging belong in `lib/`, not here.
