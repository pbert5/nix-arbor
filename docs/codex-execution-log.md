# Codex execution setup record

## 2026-10-16 — Nix Arbor #36

- Starting Nix Arbor `main`: `f0c335e97f6806777b7ed085932485317dde3aee`.
- Current policy reference inspected from Simple Evolver `main`:
  `9d53adeca84e94b22086498791b15e3248c5b69e` (`.codex/config.toml` and
  generic owner/executor/reviewer roles). Domain-specific roles and MCPs were
  excluded.
- The baseline `nixpkgs` pin provided `codex` `0.157.0`. The Codex-only pin
  selects Nixpkgs `55bfb4d7437bd4e09ab7cba58a43bd68eb310044`, which packages
  Codex `0.162.1`; it does not move the system-wide Nixpkgs input.
- Execution guidance now assigns implementation, verification, independent
  review/repair, specialist cleanup, and durable handoffs to the first-order
  owner. The primary executor performs bookkeeping only. GPT-6 Luna is the
  low-cost owner and routine specialist preference when exposed by the runtime;
  interactive leader selection stays personal.
- Generic role templates are available under `codex/roles/`. The
  `scripts/codex-roles --install` helper installs only missing templates into
  personal Codex config and refuses differing existing files. `--check` is
  read-only.
- `./tools/r640/switch` is the operator entrypoint. It requires a clean primary
  `main` checkout, correct host/flake output, and ready ZFS storage; supports
  check/build-only modes; captures rollback state; activates the exact checkout
  only on normal explicit invocation; and verifies Codex afterward.

Final commit, Codex version evidence, validation, and independent review are
recorded in issue #36 when implementation completes.
