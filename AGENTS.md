# Nix Arbor agent guide

Nix Arbor is a small composition flake for independently versioned Nix
components. Keep the root flake focused on composition; large components
belong in independent flakes and repositories.

## Workspace rules

- Default to one task, branch, and worktree. An explicit user or issue
  authorization may select an existing checkout and task branch; first check
  ownership and preserve committed, uncommitted, and unpublished work.
- Use `agent/<agent-or-role>/<task-slug>` for agent branches. Prefer the
  `scripts/agent-worktree` helper, with worktrees under `./worktrees/`.
- Read the closest `AGENTS.md` before changing a subtree. `packages/` contains
  active component checkouts; `references/` contains material for inspection,
  not dependencies to modify casually.
- Keep changes scoped to the request. Do not silently change architecture or
  port whole subsystems from a reference repository.

## Execution contract

Substantial work starts from a `PROMPT_READY` issue/workstream contract. It
names the objective and approved approach, parent, base SHA, dependencies,
ownership boundaries, shared resources and interfaces, acceptance/test/review
contracts, integration target, and human stops. Do not re-plan an approved
contract unless fresh evidence invalidates it.

The default is one task, branch, and worktree. When the user or issue explicitly
authorizes an existing checkout, inspect its actual branch, state, and ownership
first. Use one mutation owner at a time and preserve unrelated worktrees,
branches, commits, and user changes; do not assume a clean `main` branch.
Use separate durable Codex sessions for distinct substantial workstreams when
practical to protect context. Serialize shared-checkout ownership and hand off
exact SHAs between sessions; separate sessions do not permit concurrent writers.

The first-order workstream owner owns implementation, debugging, local
verification, independent review and repair, durable checkpoints, and the
terminal handoff. The owner may use bounded depth-2 specialists when the live
runtime and contract support them. Use GPT-6 Luna for owners and routine nested
specialists when available; reserve higher-cost models for evidence-backed
reasoning needs. Probe runtime model/tool availability instead of assuming
configuration guarantees it. Do not reserve root-owned review capacity or
centralize stream-local checker/reviewer routing.

The primary executor is bookkeeping-only: it tracks approved DAG readiness,
dependencies, owner lifecycle, worktree/branch provenance, and compact terminal
packets. It does not implement, debug, review diffs, interpret findings, repair,
or validate product claims. Owners return one compact terminal packet and
trust audit; raw transcripts are not executor state. The runtime thread
ceiling is a ceiling, not a task quota or reason to reserve nested capacity
centrally.

Supervision is passive-first: observe lifecycle/status, read existing output,
inspect GitHub/PR/CI/artifacts, and wait. Do not send routine status pings.
Intervene only for a concrete unblock, changed constraint, safety issue,
requested clarification, or scope/resource conflict. Owners close/reclaim
short-lived specialists after consuming their result and complete any required
review/repair loop before returning.

GitHub handoffs are durable and evidence-based. Record issue/PR, branch and
worktree, base/head SHAs, completed scope, exact validation, independent review
disposition and stable finding IDs, blockers/follow-ups, exact next action, and
a trust audit. Use authenticated REST when `gh` GraphQL compatibility fails;
diagnose token readiness separately from DNS/network capability and never
print/store token values. After GitHub mutations, perform authenticated
readback. Record pending CI once; do not poll or hold owners open for it. A
designated merge owner performs any required fresh one-shot CI gate. Bounded
multi-issue efforts include a read-only audit of native GitHub issue, PR, and
dependency relationships.

Use `/goal` for a persistent verified end state when the task warrants it.
Complete it only after acceptance evidence and required review/integration
conditions are satisfied; otherwise record the exact blocker and next action.
Merge, release, deployment, destructive migration, credential/account changes,
and physical actuation remain human stops unless the issue contract explicitly
grants the narrower authority. An open PR or pending human review is not itself
a failure.

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

## Delegation and project roles

- Follow the live task contract for delegation, concurrency, model, and depth;
  repository files do not promise runtime capabilities or impose a fixed task
  graph. GPT-6 Luna is the low-cost owner/specialist preference when exposed;
  interactive leader model selection remains personal.
- Keep stable, reusable Codex roles in the user's personal Codex configuration.
  Project `.codex/agents` contains only Nix Arbor-specific roles: Nix semantics
  and repository integration validation.
- Use delegation only when the active agent runtime supports it and the task
  contract permits it. Every concurrent mutable task gets its own
  `agent/<agent-or-role>/<task-slug>` branch and worktree unless an explicit
  authorization provides another safe boundary. Read-only reviewers
  may inspect the assigned branch without editing it.
- Preserve the assigned worktree boundary for any check that can change
  checkout state, caches, submodules, or generated files.

Nix teaching material belongs in `cheats/` and `docs/`, not in this durable
repository policy.

## Output-aware shell commands

`RTK.md` provides optional guidance for Rust Token Killer (RTK). Agents may
prefer `rtk` wrappers for high-output read-only commands such as Git, search,
tests, and Nix checks when the compact output remains sufficient. Use the
native command, or `rtk proxy`, whenever complete diagnostic evidence matters;
RTK never changes the repository's workflow or safety policy.
