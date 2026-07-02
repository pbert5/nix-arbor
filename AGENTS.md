# Agent Working Agreement

This repository follows Codex's `AGENTS.md` guidance: keep durable common
instructions here, and put path-specific rules in closer `AGENTS.md` files.
Nested files add to or override this file for their subtree.

## Required First Steps

1. Read `/home/example/.codex/RTK.md`.
2. Use `rtk` for every shell command. This is mandatory.
3. For coding tasks, load Serena's instructions first and keep using
   project-aware tools during investigation and editing.
4. Discover and use applicable MCP servers for current external facts instead
   of relying on stale model knowledge or broad web searches.
5. For Nix, NixOS, Home Manager, flakes, overlays, derivations, dev shells, or
   repo-layout work, invoke the `nixos` skill.
6. For flake architecture, module-boundary decisions, cross-class composition,
   or experiment-local flake design, invoke the `dendritic` skill as an
   appendix to `nixos`.

## Shell Commands

- Prefix every shell command with `rtk`.
- Examples: `rtk git status`, `rtk nixos-rebuild build --flake .#desktoptoodle`.
- If raw command behavior is required, use `rtk proxy <command>`.
- Verify availability with `rtk --version` when uncertain.
- CODEX: dont run background commands, just runn them in the foreground

## Repo Defaults

- Prefer declarative Nix configuration over ad-hoc imperative scripts.
- Keep system behavior encoded in Nix whenever practical.
- Favor small, composable modules with clear ownership.
- Prefer the simplest minimal change. Use native or standard-library features
  before new dependencies or abstractions, and avoid speculative generality.
- Beyond the core host age encryption key installed during enrollment, manage
  machine setup and cluster behavior declaratively through the flake.

## Tooling

- Use `tool_search` when an applicable MCP tool is deferred or not visible.
- Use Serena for semantic code navigation and edits when it fits the file type.
  - Use Serena for Python work when semantic navigation saves context or reduces mistakes:
    - Prefer Serena when a task touches 3 or more files, requires finding definitions or callers, involves refactors, or needs project-structure understanding.
    - Use Serena for class/function/method navigation, reference tracing, signature changes, and low-token edits in larger Python subprojects.
    - Do not force Serena for tiny scripts, simple syntax fixes, formatting-only edits, or traceback-local bugs where the failing line is already clear.
    - Pair Serena with normal verification tools such as pytest, ruff, mypy, or the narrowest relevant project check.
- for manipulating nix code:
  - Serena for repo navigation and low-token edits.
  - nixd for Nix-aware LSP behavior, options, packages, and cross-file analysis
  - MCP-NixOS for accurate package/options lookup instead of hallucinated option names. It provides current NixOS packages, options, Home Manager options, nix-darwin, flakes, Noogle, and related Nix resources.
  - 
- Use shell tools for builds, tests, Git, generated output, and cases where
  semantic tools do not fit.
- Use `apply_patch` for small line-oriented edits.
- When work genuinely requires the whole repository, read
  `repomix-output.xml` instead of scanning every source file individually.

## Verification

- Before handoff, run the narrowest check that exercises the changed behavior.
- Do not run deployments or activation commands such as `clusterctl deploy` or
  `nixos-rebuild switch` unless the user explicitly grants permission for that
  specific deployment.
- Prefer build and evaluation checks when deployment permission has not been
  granted.
