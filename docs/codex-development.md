# Codex development

This repository keeps shared MCP defaults in [.codex/config.toml](../.codex/config.toml).
The file is project-local and loaded only for trusted projects. It contains no
credentials. Nix Arbor enables only its existing optional Playwright and
Context7 integrations; it does not import Simple Evolver's domain-specific
roles or MCP services.

Use the repository helper to inspect or change only the `enabled` flags:

```sh
./scripts/codex-mcp list
./scripts/codex-mcp enable playwright
./scripts/codex-mcp disable context7
./scripts/codex-mcp all disable
./scripts/codex-mcp all enable
```

Changes are made to committed config, so review or revert them like any other
repository change. Restart Codex after changing a server. Do not put tokens in
this repository. Verify availability with `codex mcp list` or the Codex MCP
UI, and stop any temporary server process after manual checks.

## RTK

RTK is an optional output-reduction wrapper, not a repository policy layer.
Use it when convenient (`rtk read`, `rtk git`, or `rtk err`), while preserving
the commands and safety requirements in `AGENTS.md`. Do not run `rtk init` as
part of setup: it changes user-level assistant hooks and is outside this
repository's scope.

## Execution roles and `/goal`

For substantial work, start from the current issue contract and closest
`AGENTS.md`. Keep the working context to the objective, approved design,
dependencies, ownership/shared-resource boundaries, interfaces,
acceptance/test/review contracts, integration target, and human stops. Read
broader history only when needed; avoid dumping issue histories, logs, or
transcripts into context.

The current policy reference is Simple Evolver `main`; inspect its live
`.codex/config.toml` and generic roles before adapting policy. Nix Arbor keeps
project roles Nix-specific and does not import domain roles or optional MCP
servers. In normal burn, use `gpt-6.1-terra` for first-order owners and
nested implementation specialists: `low` effort for straightforward bounded work,
`medium` for more involved implementation and debugging.
Within execution work, reserve Luna for primitive execution actions. Pass model and effort explicitly when
personal defaults differ; leave other burn tiers and active user-owned runs
unchanged. Probe the active model/tool runtime because project settings
do not guarantee capabilities. The interactive leader's model remains a
personal choice.

Reusable generic templates are in `codex/roles/`. Inspect them, then use
`scripts/codex-roles --install` to copy missing roles into personal
`CODEX_HOME/agents`; it leaves identical files alone and refuses to overwrite
different files. `scripts/codex-roles --check` is read-only. Project-local
`.codex/agents/` remains limited to Nix semantics and repository integration.

`PROMPT_READY` is the design-before-prompt gate. Do not launch implementation
from an ambiguous issue or re-plan an approved contract without fresh evidence.
The primary executor handles bookkeeping only: approved DAG readiness,
dependencies, owner lifecycle, branch/worktree provenance, and compact
terminal packets. The owner implements, debugs, verifies, obtains independent
review, repairs findings, and returns a compact terminal packet with trust
audit. Do not centralize stream-local review/check/repair or reserve nested
capacity at the root. Owners close/reclaim short-lived specialists after
consuming their results.

Use Codex `/goal` for a persistent verified end state when the task warrants
it. Complete it only after acceptance evidence and required review/integration
conditions are satisfied; otherwise record the exact blocker and next action.
Keep GitHub issues and Session handoffs as the durable project ledger.

## Supervision, GitHub and safety

Supervision is passive-first. Observe lifecycle/status, read existing output,
inspect GitHub/PR/CI/artifacts, and wait. Send input only for a concrete
unblock, changed constraint, safety issue, requested clarification, or
scope/resource conflict. Do not send routine status pings.

Credentials are readiness signals only: never print, store, or include tokens
in capsules, logs, commits, or handoffs. If a high-level GitHub query fails due
to GraphQL compatibility, use authenticated REST; distinguish token readiness
from DNS/network failures and read back mutations. Record pending CI once,
without polling. Bounded multi-issue efforts include a read-only audit of
native GitHub issue/PR relationships.

Every handoff names issue/PR, branch/worktree, base/head, scope, exact checks,
independent review disposition and stable finding IDs, follow-ups, blockers,
exact next state, and a trust audit covering confidence, least-trusted claims,
untested paths, possible misunderstandings, and highest-value next evidence.
Protected/default branches, publishing, deployment, destructive migrations,
account changes, and physical actuation remain human stops unless explicitly
authorized.

## R640 operator entrypoint

The reviewed operator tool is `./tools/r640/switch`. Run it only from a clean
primary `main` checkout on the R640 host. `--check` performs preflight without
sudo or activation; `--dry-run` builds the exact `r640-0` flake output without
activating it. A normal invocation prompts for sudo, records rollback state,
switches that checkout's `#r640-0`, and verifies Codex afterward. See the
script's `--help` and [R640 switch guide](r640-switch.md). Codex and
codex-switch use reproducible Nix packages; do not use global npm installation
or curl-pipe shell commands.
