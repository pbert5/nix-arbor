# Agent-first workflows

The default is one task, branch, and worktree. Agents normally work in sibling
directories under `./worktrees/`. Explicit user or issue authorization may
select an existing checkout and task branch after checking its state and
ownership; preserve committed, uncommitted, and unpublished work.

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
debugging, local verification, independent review/repair, durable checkpoints,
and terminal packet. It may use bounded depth-2 specialists when the task
contract and live runtime allow it. Prefer GPT-6 Luna for owners and routine
nested specialists when exposed by the runtime. Use a higher-cost model only
when fresh evidence or the contract needs it. Configuration describes desired
capabilities, not guarantees; probe the active runtime. Do not reserve nested
capacity or root-owned stream-local reviewer/checker slots.

The primary executor is bookkeeping-only. It tracks the approved DAG,
dependencies, owner lifecycle, worktree/branch provenance, and compact terminal
packets. It does not implement, debug, review diffs, interpret findings, repair,
or validate product claims. Owners close/reclaim their specialists and finish
required review/repair before returning. Supervise passive-first and intervene
only for a concrete unblock, changed constraint, safety issue, requested
clarification, or scope/resource conflict; routine status pings are forbidden.

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
This repository registers two normal Nix specialist and integration-test roles
and five self-contained opt-in Terra/high variants. These do not define a generic
execution topology.

Use delegation only when the task contract and live client support it. Treat
the current runtime concurrency and depth as capabilities to observe, not
limits to infer from repository configuration. Keep concurrent mutable work
isolated to separate branches and worktrees unless
the explicit authorization supplies another safe boundary. A shared checkout
has one mutation owner at a time. Use separate durable Codex sessions for
distinct substantial workstreams when practical; serialize ownership and hand
off exact SHAs. Use only proven nonmutating checks for read-only roles. Their
instructions are behavioral boundaries, not a separate OS sandbox; subagents
inherit parent sandbox and approval settings. A remote repository configuration
only applies where that configuration is actually loaded, not automatically to
a desktop session issuing remote commands.

A handoff records issue/PR, branch/worktree, base and final commit, summary,
exact validation, review outcome and stable finding IDs, blockers, follow-ups,
trust audit, and exact next action. Independent review is required by the
contract: report `PASS`, `PASS_WITH_FOLLOWUPS`, or `CHANGES_REQUIRED` against an
exact head SHA. The owner records findings durably, repairs blocking findings,
and obtains re-review before returning a terminal packet. Use authenticated
REST if `gh` GraphQL fails; distinguish token readiness from DNS/network
failure, never expose token values, and read back GitHub mutations. Record
pending CI once without polling; the authorized merge owner performs any
required one-shot gate. Multi-issue work includes a read-only native GitHub
relationship audit.

### High-burn session option

High-burn is an explicit, session-scoped opt-in, never a quota-driven or automatic
default. It replaces otherwise-Luna subagents with `gpt-6.1-terra` / `high`
throughout the existing task topology, including owners, workers, prompt loaders,
reviewers, verifiers, scouts and nested helpers. It does not require a benchmark,
pilot, extra team layers or a new planning framework. Ordinary product tests and
independent review remain required by the task contract.

Select from the five self-contained `*-terra-high` compatibility variants:
`architect-researcher`, `implementer`, `reviewer`, `nix-specialist` and
`integration-test`. Their TOML layers set the model and effort and
the same defaults for descendants. Normal Nix specialist and integration-test
roles remain registered; generic normal roles belong in personal configuration.

For generic/personal roles, explicitly pass `model="gpt-6.1-terra"` and high
reasoning effort on every spawn, including nested spawns, using the host's
supported effort parameter. Explicit spawn choices override defaults. Do not
select a Luna-pinned personal role and assume inheritance changes it. If the
runtime cannot apply the requested override, report that limitation rather than
silently substituting a model.

A CLI session can supply fallback defaults without editing user configuration:

```sh
codex -c 'agents.default_subagent_model="gpt-6.1-terra"' \
  -c 'agents.default_subagent_reasoning_effort="high"'
```

These are defaults, not enforcement; use explicit high-burn role/model selection
as above. Keep the interactive leader's model separate. A prompt-only opt-in uses
the same explicit spawn mapping without the CLI defaults. Ending the session
ends this opt-in. Do not change global config, security settings, persistent thread
limits or the ordinary Luna mode. Project-local `[profiles]` are not used because the
current Codex documentation says they are ignored at project scope.

Reference: [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-reference).
Model availability is runtime-dependent; configuration alone does not establish
that the selected model is available.

#### High-burn parallelism and nesting

Retain the established multi-tier owner -> reviewer/worker -> focused helper
topology; do not flatten it into one large agent or force everything through a
single serial workstream. Dispatch as many independent READY workstreams as the
actual harness supports, while each owner manages capacity for its own review and helper
children. Nested agents consume capacity too: coordinate the whole active tree,
close finished agents after collecting their handoffs, and immediately dispatch
newly READY useful work. Do not invent work to occupy slots, violate dependencies
or permit concurrent writers to overlap.

The repository's ordinary ceiling remains six spawned-agent threads, excluding
the primary thread. High-burn defaults to maximum useful parallelism: raise that ceiling for this session only,
using a positive integer established from the selected harness's reported
capacity and supported configuration. No universal maximum or unlimited sentinel
is assumed. For a compatible CLI, set `HIGH_BURN_THREADS` to that verified integer
before using this session-only override alongside the model defaults:

```sh
codex -c "agents.max_concurrent_threads_per_session=${HIGH_BURN_THREADS:?set to the verified supported spawned-thread cap}" \
  -c 'agents.default_subagent_model="gpt-6.1-terra"' \
  -c 'agents.default_subagent_reasoning_effort="high"'
```

A prompt-only request does not itself raise the harness ceiling. If the selected
host cannot expose or change it, use its available slots and report that bound;
do not claim maximum capacity was verified. On V1 only, preserve enough nesting
depth for the established tiers with a supported session-only `agents.max_depth`
override after checking the installed version. The current schema says that key
is ignored by V2; do not use it to promise nesting there or switch backends.
The historical project `max_depth = 2` remains configured, but does not prove
enforcement in V2. Neither documented settings
nor a higher requested number prove actual runtime capacity.

Ordinary correctness checks and independent review remain required for
substantive work.

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
authority and required checks/reviews pass. Explicit user or issue
authorization may select an existing checkout and task
branch for one mutation owner. Inspect the actual branch and state first; do not
assume `main` or a clean checkout. Check that no other writer owns the touched
files and preserve unrelated worktrees, branches, commits, and user changes:

```text
isolated worktree -> implement -> validate -> commit -> review/check
    -> merge into intended base -> verify the merged base -> clean up
```

After integration, verify `git status`, inspect a recent graph with
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
