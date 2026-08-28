# Nix Arbor agent guide

Nix Arbor is a small composition flake for independently versioned Nix
components. Keep the root flake focused on composition; large components
belong in independent flakes and repositories.

## Workspace rules

- One agent task = one branch = one worktree. Do not edit another agent's
  checkout or use the primary checkout for task changes.
- Use `agent/<agent-or-role>/<task-slug>` for agent branches. Prefer the
  `scripts/agent-worktree` helper, with worktrees outside this repository.
- Read the closest `AGENTS.md` before changing a subtree. `packages/` contains
  active component checkouts; `references/` contains material for inspection,
  not dependencies to modify casually.
- Keep changes scoped to the request. Do not silently change architecture or
  port whole subsystems from a reference repository.

## Change and handoff expectations

- Prefer native Nix and Git commands. Run the narrowest useful checks, then
  `nix flake check` when the flake or shared tooling changes.
- Format changed Nix files with `nix fmt` and make coherent local commits.
- Do not use `git reset --hard`, `git clean -fdx`, force-push, or destructive
  cleanup as shortcuts. Agents do not push unless explicitly asked.
- A normal completed task merges its validated commit into the identified base
  branch, verifies the merged base, then removes its clean worktree and stale
  merged local agent branch. Stop at a committed handoff instead when
  validation fails, work is incomplete, conflicts remain, coordination or
  review is required, deployment approval is needed, the base is unclear, or
  the merge could overwrite newer work.
- After merging, inspect `git status` and a recent `git log --graph`, then rerun
  the relevant validation against the merged base. Never treat a successful
  merge exit code as sufficient.
- Resolve conflicts semantically by inspecting both sides; do not choose whole
  files with `ours` or `theirs` as a shortcut. Preserve independent entries in
  sensitive integration and workflow files.
- A handoff names the branch and worktree, commit SHA(s), summary, changed
  files, validation, known issues, and review readiness. See
  `docs/agent-workflows.md`.

## Subagent execution

- For substantial tasks, the owning agent constructs a dependency graph, fans
  out independent ready work to focused subagents, retains dependent work in a
  waiting queue, and dispatches it as prerequisites complete.
- Keep useful bounded work flowing when ready; continuously synthesize findings
  and retain architecture, integration, and final decisions in the owning
  session. Use the repository roles deliberately rather than spawning generic
  clones.
- Read-only research, testing, and review agents may share repository
  visibility only when their commands are non-mutating. Give tests or tools
  that may change checkout state, caches, submodules, or generated files an
  isolated worktree. Every concurrent mutable implementation task gets its own
  `agent/<agent-or-role>/<task-slug>` branch and worktree; never let mutable
  agents edit the same checkout concurrently.

Nix teaching material belongs in `cheats/` and `docs/`, not in this durable
repository policy.

## Output-aware shell commands

`RTK.md` provides optional guidance for Rust Token Killer (RTK). Agents may
prefer `rtk` wrappers for high-output read-only commands such as Git, search,
tests, and Nix checks when the compact output remains sufficient. Use the
native command, or `rtk proxy`, whenever complete diagnostic evidence matters;
RTK never changes the repository's workflow or safety policy.
