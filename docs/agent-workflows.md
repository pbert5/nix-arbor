# Agent-first workflows

The repository contract is **one task = one branch = one worktree**. The
primary checkout is for integration and review; agents work in sibling
directories under `./worktrees/`.

## Starting work

The helper creates `agent/<agent-or-role>/<task-slug>` and initializes
submodules:

```sh
./scripts/agent-worktree new workspace-infra luna
cd worktrees/agent-luna-workspace-infra
nix develop
```

Native Git equivalent:

```sh
git worktree add -b agent/luna/my-task worktrees/agent-luna-my-task HEAD
git -C worktrees/agent-luna-my-task submodule update --init
```

Start Codex or Claude only after entering that worktree:

```sh
codex
claude
```

## PROMPT_READY launch contract

Before implementation, a design/approach is approved and recorded in the
tracking issue or workstream issue. Mark it `PROMPT_READY` only when the issue
contains all of the following:

- objective and design/approach;
- parent/tracking issue, base branch and SHA, dependencies, and integration
  target;
- ownership: may modify, may read, and must not modify;
- shared resources and interfaces;
- acceptance, test, and review contracts; and
- human-stop boundaries.

The prompt-loader retrieves this minimum current capsule from GitHub and the
relevant repository instructions. It may perform broad history/GitHub
retrieval, but passes the executor and owner compact current facts rather than
raw histories or logs. A PROMPT_READY owner executes the approved contract;
fresh evidence that invalidates it is reported as a blocker for an explicit
decision, not silently re-planned.

The first-order owner owns one issue, worktree, branch, and (normally) early
draft PR. It may implement directly and may reserve bounded depth-2 capacity
for scouts, advisers, implementers, verifiers, reviewers, or repair workers.
It owns local verification and review/repair, durable checkpoints, and the
terminal packet. The thin primary executor routes only predefined nodes and
records state; it does not become the architect, implementer, debugger, or
reviewer.

Codex Cloud environments can select `scripts/codex-setup` as their supported
setup script. It initializes direct submodules and evaluates the dev shell
non-interactively; the cloud image must provide Nix. Run non-interactive
checks such as `nix flake check`; authentication and personal settings stay
outside the repository. Submodules are explicit: `git submodule update --init`.
If a child repository has its own valid
`.gitmodules`, initialize that child recursively with
`git -C packages/<component> submodule update --init --recursive`.

## Dependency-aware delegation

For any substantial task, the approved design should include a lightweight,
ephemeral task graph instead of doing the whole task serially. Claude agents
should apply the same model when their current agent system supports
delegation. The thin executor keeps the approved graph in session state; no
persistent task database is needed.

Classify each task as one of:

- `READY`: all prerequisites are complete and a worker can start now.
- `BLOCKED`: waiting on named prerequisite tasks; keep it in a queue.
- `INTEGRATION`: authorized owner or human-owned composition/boundary work after implementation.
- `REVIEW`: independent adversarial inspection near the end.
- `VALIDATION`: focused or final checks against the integrated result.

After a graph is approved, the executor identifies READY tasks and dispatches
independent work concurrently. When an owner finishes, it consumes the
terminal packet, updates the graph, and immediately dispatches newly
unblocked tasks. Architecture, decomposition, semantic decisions, integration
preparation, and synthesis belong to the named owner or human authority, not
the executor. Do not create busy-work merely to fill a slot: useful bounded
work takes priority over maximizing concurrency. Do not wait for an entire
wave when one completed prerequisite already unblocks useful work.

For each graph entry, track at least its task ID, state, prerequisites, owner,
write set/worktree (if mutable), and deliverable or validation evidence. A
failed prerequisite blocks its dependents until the authorized owner or human
repairs, replaces, or cancels it; record that decision in the handoff.

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

The workstream owner remains responsible for its bounded objective, local
implementation, review/repair, and evidence. The executor only performs the
mechanical lifecycle and routing defined by the approved graph. Use the
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
while E remains `BLOCKED`; the executor should dispatch F immediately.

### Delegation and handoff

Use the small role briefs in `.agents/roles/`. Claude wrappers live in
`.claude/agents/`, and Codex custom agents are registered under `.codex/agents/`.

A normal handoff includes branch, worktree path, commit SHA(s), summary, files
changed, validation, known issues, and whether it is ready for review. A
reviewer should inspect `git diff <base>...<branch>` and the branch's checks
before cherry-picking or merging.

Concurrency is an observed runtime capability, not a promised topology. The
executor must retain an explicit nested-capacity reserve before dispatching
first-order owners; an owner may consume only its bounded depth-2 allowance.
Do not invent project configuration keys for DAGs or scheduling.

Claude should follow the same dependency-aware delegation and safe worktree
principles described above where its current agent system supports them,
without copying Codex-specific configuration or mechanisms.

### Component ownership and pins

`packages/arbor-manager` and `packages/arbor-registry` are Git submodules
backed by their standalone repositories. Change implementation only in a
child-repository branch/worktree, then update the parent gitlink. Root `main`
pins component `main`; root `arbor-infra-dev` pins component `arbor-infra-dev`.
Remote flake inputs remain authoritative for normal builds; initialized
submodules are selected locally only with `--override-input`.

## State machine and supervision

Use these machine-actionable states:

`READY` -> `RUNNING` -> `VERIFYING` -> `READY_FOR_REVIEW` -> `REVIEWING` ->
`READY_FOR_INTEGRATION` -> `INTEGRATING` -> `VALIDATING` -> `DONE`.

An authorized transition may instead enter `BLOCKED_DEPENDENCY`,
`BLOCKED_SHARED_RESOURCE`, `BLOCKED_ENVIRONMENT`, `BLOCKED_AUTHORIZATION`,
`BLOCKED_AMBIGUOUS`, `BLOCKED_EXTERNAL`, or `BLOCKED_DESTRUCTIVE`. The owner
provides evidence and the executor records the deterministic transition;
semantic decisions are delegated to the responsible owner/reviewer or human.

Supervision is passive-first: observe lifecycle and status, read already
available output, inspect GitHub/PR/CI/artifacts, and wait. Do not send routine
status pings or steer an active owner. Intervene only to unblock concretely,
apply a changed constraint, address safety, answer a requested clarification,
or resolve a scope/resource conflict.

## Review and terminal handoff

Independent review reports `PASS`, `PASS_WITH_FOLLOWUPS`, or
`CHANGES_REQUIRED`. Every substantive finding has a stable ID (for example
`RF-001`) and records blocking rationale, evidence, scope, affected SHA,
disposition, and verification. Review history is durable; do not silently
rewrite or erase findings.

The owner’s terminal packet is compact and always includes:

- branch/worktree and base/head SHAs;
- draft PR (or explicit absence), completed scope, and validation evidence;
- open finding IDs/follow-ups and blockers;
- exact next state; and
- a trust audit: confidence band, least-trusted claims, untested paths,
  possible misunderstandings, and the next evidence that would reduce
  uncertainty most.

Publish a meaningful issue checkpoint during substantial work and an
end-of-session handoff to the issue/PR. The executor consumes packets, not
local transcripts. A designated integration session must run a bounded,
read-only relationship audit before completing a substantial multi-issue
effort, comparing intended issue/PR relationships with native GitHub state.

## Completion and merge

For a normal task, a validated agent branch may merge into its identified
development/integration base only when the issue contract grants that
authority and required checks/reviews pass:

```text
isolated worktree -> implement -> validate -> commit -> review/check
    -> merge into intended base -> verify the merged base -> clean up
```

After the merge, verify `git status`, inspect a recent graph with
`git log --graph --decorate --oneline`, and rerun the relevant checks against
the merged base. For Nix Arbor this normally includes `nix flake check` and
the focused component checks. A successful `git merge` exit code alone is not
completion.

Protected/default branches, releases, deployments, destructive migrations,
publishing, and physical actuation remain human boundaries unless explicitly
authorized. An early draft PR is the normal durable handoff. Do not merge when
validation fails, the task is incomplete, conflicts remain,
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

The launch directory is not sacred: owners deliberately enter their assigned
worktree before mutation. Preserve unrelated worktrees, branches, user
changes, and uncommitted state. One concurrently mutating workstream owns one
worktree/branch. Native commands remain useful when the helper is unavailable:

```sh
git worktree add -b agent/name/task ./worktrees/agent-name-task origin/main
git worktree list
git worktree remove ./worktrees/agent-name-task
git worktree prune
git branch --merged main
```

`packages/` child repositories have independent branches and worktrees; this
helper manages Nix Arbor only. The `references/flake-devbox` submodule is
legacy/reference material: inspect it, but do not normally modify it or make
new code depend on it.
