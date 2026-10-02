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

The prompt-loader may retrieve broad history and then pass compact current
facts rather than raw logs. A PROMPT_READY owner executes the approved
contract; fresh evidence that invalidates it is reported for resolution rather
than silently re-planned.

The first-order owner owns its issue, worktree, branch, implementation,
verification, review/repair, durable checkpoints, and terminal packet. It may
use bounded specialists when the task contract and live runtime allow it. The
primary executor owns cross-workstream dependencies, lifecycle, concurrency,
and durable orchestration state; it does not implement or review stream-local
changes.

Codex Cloud environments can select `scripts/codex-setup` as their supported
setup script. It initializes direct submodules and evaluates the dev shell
non-interactively; the cloud image must provide Nix. Run non-interactive
checks such as `nix flake check`; authentication and personal settings stay
outside the repository. Submodules are explicit: `git submodule update --init`.
If a child repository has its own valid
`.gitmodules`, initialize that child recursively with
`git -C packages/<component> submodule update --init --recursive`.

## Project roles and delegation

Stable, reusable Codex roles (including prompt loaders, executors, owners,
implementers, verifiers, and reviewers) belong in personal Codex configuration.
This repository registers only the Nix specialist and integration-test roles
under `.codex/agents/`, `.agents/roles/`, and `.claude/agents/`; they do not
define a generic execution topology.

Use delegation only when the task contract and live client support it. Treat
the current runtime concurrency and depth as capabilities to observe, not
limits to infer from repository configuration. Keep mutable work isolated to
one branch and worktree. Use a non-mutating mode or isolated worktree for
checks that can change caches, submodules, generated files, or lock files.

A handoff records the branch/worktree, base and final commit, summary,
validation, review outcome, blockers, follow-ups, and exact next action. An
independent reviewer inspects the assigned diff and evidence; the owner repairs
blocking findings and requests re-review before returning a terminal packet.

### Component ownership and pins

`packages/arbor-manager` and `packages/arbor-registry` are Git submodules
backed by their standalone repositories. Change implementation only in a
child-repository branch/worktree, then update the parent gitlink. Root `main`
pins component `main`; root `arbor-infra-dev` pins component `arbor-infra-dev`.
Remote flake inputs remain authoritative for normal builds; initialized
submodules are selected locally only with `--override-input`.

## Lifecycle and supervision

Track the lifecycle states needed by the active workstream. Record blockers
with evidence and name the authority or dependency needed to resolve them;
repository guidance does not prescribe a universal state machine.

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
