# Agent-first workflows

The repository contract is **one task = one branch = one worktree**. The
primary checkout is for integration and review; agents work in sibling
directories under `../nix-arbor-worktrees/`.

## Starting work

The helper creates `agent/<agent-or-role>/<task-slug>` and initializes
submodules:

```sh
./scripts/agent-worktree new workspace-infra luna
cd ../nix-arbor-worktrees/agent-luna-workspace-infra
nix develop
```

Native Git equivalent:

```sh
git worktree add -b agent/luna/my-task ../nix-arbor-worktrees/agent-luna-my-task HEAD
git -C ../nix-arbor-worktrees/agent-luna-my-task submodule update --init
```

Start Codex or Claude only after entering that worktree:

```sh
codex
claude
```

Codex Cloud environments can select `scripts/codex-setup` as their supported
setup script. It initializes direct submodules and evaluates the dev shell
non-interactively; the cloud image must provide Nix. Run non-interactive
checks such as `nix flake check`; authentication and personal settings stay
outside the repository. Submodules are explicit: `git submodule update --init`.
If a child repository has its own valid
`.gitmodules`, initialize that child recursively with
`git -C packages/<component> submodule update --init --recursive`.

## Dependency-aware delegation

For any substantial task, the owning Codex agent should use a lightweight,
ephemeral task graph instead of doing the whole task serially. Claude agents
should apply the same model when their current agent system supports
delegation. The lead keeps the graph in session state; no persistent task
database is needed.

Classify each task as one of:

- `READY`: all prerequisites are complete and a worker can start now.
- `BLOCKED`: waiting on named prerequisite tasks; keep it in a queue.
- `INTEGRATION`: lead-owned composition or boundary work after implementation.
- `REVIEW`: independent adversarial inspection near the end.
- `VALIDATION`: focused or final checks against the integrated result.

At the start, inspect the request and repository, decompose the work, identify
all ready tasks, and dispatch independent work concurrently. When a worker
finishes, consume its result, update the graph, and immediately dispatch newly
unblocked tasks. Keep doing useful lead work—architecture, decisions,
integration preparation, and synthesis—while workers run. Do not create
busy-work merely to fill a slot: useful bounded work takes priority over
maximizing concurrency. Do not wait for an entire wave when one completed
prerequisite already unblocks useful work.

For each graph entry, track at least its task ID, state, prerequisites, owner,
write set/worktree (if mutable), and deliverable or validation evidence. A
failed prerequisite blocks its dependents until the lead repairs, replaces, or
cancels it; record that decision in the handoff.

There are two independent forms of concurrency:

1. Read-only reasoning concurrency covers repository audits, upstream research,
   test inventories, failure investigation, and reviews. These agents return
   findings and do not need separate worktrees when their commands are
   non-mutating.
2. Mutable implementation concurrency covers agents that edit files. One
   mutable task owns one branch and one worktree. Partition write sets to avoid
   overlap; serialize tasks that must change the same files, then integrate
   branches in dependency order rather than completion order.

Tests and investigations that can update ignored files, build outputs,
submodule state, caches, or locks are mutable for isolation purposes even when
they do not commit source changes; run them in a dedicated worktree or use a
strictly non-mutating mode.

The lead remains responsible for the objective, decomposition, dependency
ordering, architecture, conflict resolution, integration, final validation,
and merge. Subagents own bounded deliverables and report evidence. Use the
specialized roles deliberately: architect/researcher for discovery,
implementer for isolated changes, nix-specialist for Nix semantics,
integration-test for workflow checks, and reviewer for independent challenge.

Prefer several waves when the task warrants it:

```text
discovery -> implementation -> integration -> independent review/validation
         -> targeted fixes -> final validation -> merge
```

Review and validation should fan out again near the end. The reviewer should
not be the agent that implemented the reviewed change when an independent
context is available.

### Example task graph

For a hypothetical task, “Add a new machine deployment subsystem”:

```text
DISCOVERY WAVE (all READY, concurrent)
A  inspect Arbor Manager
B  inspect legacy deployment code
C  research native nixos-rebuild deployment
D  audit existing tests

IMPLEMENTATION WAVE
E  deployment library          <- A + B + C
F  test fixtures                <- A + D
G  documentation                <- C

INTEGRATION
H  integrate deployment + tests <- E + F + G

REVIEW / VALIDATION (concurrent, after H)
I  independent reviewer
J  Nix specialist review
K  integration tests

FINISH
L  targeted fixes               <- I + J + K
M  final validation             <- L
N  merge                        <- M
```

Tasks E, F, and G enter the waiting queue initially and are dispatched as
their prerequisites complete. If only A and D finish, F becomes `READY` even
while E remains `BLOCKED`; the lead should dispatch F immediately.

### Delegation and handoff

Use the small role briefs in `.agents/roles/`. Claude wrappers live in
`.claude/agents/`, and Codex custom agents are registered under `.codex/agents/`.

A normal handoff includes branch, worktree path, commit SHA(s), summary, files
changed, validation, known issues, and whether it is ready for review. A
reviewer should inspect `git diff <base>...<branch>` and the branch's checks
before cherry-picking or merging.

Codex project configuration enables six concurrent spawned-agent threads. This
is the supported `agents.max_concurrent_threads_per_session` setting and does
not include the primary lead thread. It is a bounded worker pool, not a task
queue: dependency tracking and ready/waiting dispatch remain lead behavior.
Do not invent project configuration keys for DAGs or scheduling.

Claude should follow the same dependency-aware delegation and safe worktree
principles described above where its current agent system supports them,
without copying Codex-specific configuration or mechanisms.

### Component publication and deployment locks

Child flakes are independently versioned. During development, a checkout under
`packages/` and `nix-arbor-local` path overrides are appropriate for focused
testing and integration experiments. They do not identify what a physical host
will consume.

When component work is ready to be consumed by the root integration branch or
deployment candidate, the owning/integrating agent must commit and validate the
component, publish the validated commit to its canonical repository when
authorized, and update the root input and `flake.lock` to that exact immutable
revision. Then run root checks and the deployment build without local override
helpers, and prove the resolved revisions with `nix flake metadata` or the
`nix-arbor-locked-metadata` app. Do not update unrelated inputs.

Local component success is not physical integration success. A deployment
handoff must report the exact component SHAs in the lock; a nested checkout,
passing local override test, or successful evaluation with an implicit path
override is not deployment readiness.

## Completion and merge

For a normal task, a validated agent branch merges itself into its identified
base branch before reporting completion:

```text
isolated worktree -> implement -> validate -> commit -> review/check
    -> merge into intended base -> verify the merged base -> clean up
```

After the merge, verify `git status`, inspect a recent graph with
`git log --graph --decorate --oneline`, and rerun the relevant checks against
the merged base. For Nix Arbor this normally includes `nix flake check` and
the focused component checks. A successful `git merge` exit code alone is not
completion.

Do not merge when validation fails, the task is incomplete, conflicts remain,
another agent is changing the same integration area, review was explicitly
requested first, production/deployment approval is required, the base is
unclear, or the merge could discard newer work. In those cases commit a
handoff and report the reason.

Resolve conflicts semantically: inspect both sides and preserve independent
entries. Never select whole-file `ours` or `theirs` merely to make a conflict
disappear. Take extra care with `flake.nix`, `flake.lock`, `.gitmodules`,
integration modules, `DEV.md`, `AGENTS.md`, `CLAUDE.md`, `Justfile`, and
`.vscode/tasks.json`.

## Worktree lifecycle and safe cleanup

```sh
./scripts/agent-worktree list
./scripts/agent-worktree status
./scripts/agent-worktree remove my-task
./scripts/agent-worktree cleanup-merged
./scripts/agent-worktree prune
```

The helper refuses to remove a dirty or unmerged agent branch by default and
never runs `git reset --hard` or `git clean`. A clean agent branch whose
commits are ancestors of the configured base is a candidate for
`cleanup-merged`: the helper removes its worktree, prunes its metadata, and
deletes only the merged local branch. It never deletes remote branches.
Inspect `git worktree list` and `agent-worktree status` first; leave branches
that are dirty, unmerged, or still needed by another active effort in place.
`--force` is available only on an explicitly named `remove` command. Bulk
cleanup never accepts force.

Native commands remain useful:

```sh
git worktree add -b agent/name/task ../nix-arbor-worktrees/agent-name-task HEAD
git worktree list
git worktree remove ../nix-arbor-worktrees/agent-name-task
git worktree prune
git branch --merged main
```

`packages/` child repositories have independent branches and worktrees; this
helper manages Nix Arbor only. The `references/flake-devbox` submodule is
legacy/reference material: inspect it, but do not normally modify it or make
new code depend on it.
