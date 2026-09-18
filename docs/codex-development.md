# Codex development

This repository keeps its shared MCP defaults in [.codex/config.toml](../.codex/config.toml).
The file is project-local and is loaded only for trusted projects. It contains
no credentials:

- `playwright` starts the official `@playwright/mcp` stdio server through `npx`.
- `context7` uses Context7's hosted endpoint.

Use the repository helper to inspect or change only the `enabled` flags:

```sh
./scripts/codex-mcp list
./scripts/codex-mcp enable playwright
./scripts/codex-mcp disable context7
./scripts/codex-mcp all disable
./scripts/codex-mcp all enable
```

Changes are intentionally made to the committed config, so review or revert
them like any other repository change. Restart Codex after changing a server.
The hosted endpoint may still require its own OAuth/account policy; do not put
tokens in this repository. If hosted access is unavailable, the official local
alternative is `npx -y @upstash/context7-mcp` (not enabled by default). Verify
availability with `codex mcp list` or the Codex MCP UI, and stop any temporary
server process after manual checks.

## RTK

RTK is an optional output-reduction wrapper, not a repository policy layer.
Use it when convenient (`rtk read`, `rtk git`, or `rtk err`), while preserving
the commands and safety requirements in `AGENTS.md`. Do not run `rtk init` as
part of setup: it changes user-level assistant hooks and is outside this
repository's scope.

## Prompt capsules and `/goal`

For substantial work, the prompt-loader (or the owner working from the issue)
hydrates a compact capsule only after reading the closest `AGENTS.md`. A
capsule contains the current objective, approved design, parent, base/head,
dependencies, ownership and shared-resource boundaries, interfaces,
acceptance/test/review contracts, integration target, and human stops. Broad
GitHub/history retrieval belongs in the loader or a bounded scout; do not dump
large issue histories, logs, or transcripts into the executor context.

`PROMPT_READY` is the design-before-prompt gate. Do not launch implementation
from an ambiguous issue and do not re-plan an approved capsule without fresh
evidence. The primary executor receives capsules, stream states, and terminal
packets—not raw owner transcripts—and keeps nested capacity available for the
owner’s bounded depth-2 specialists.

Use Codex `/goal` for the persistent, verified end state of a long-running
session. It is distinct from mutable issue decomposition: the issue may gain
checkpoints, blockers, or workstream details while `/goal` remains the tested
completion contract. Close the goal only after the acceptance evidence and
required review/integration conditions are satisfied; otherwise preserve the
exact next state and blocker in the terminal packet.

## Passive supervision and safety

Supervision is passive-first. Observe lifecycle/status, read existing output,
inspect GitHub/PR/CI/artifacts, and wait. Do not send routine pings or steer
an active owner. Send input only for a concrete unblock, changed constraint,
safety issue, requested clarification, or scope/resource conflict. Keep
credentials as readiness signals only: never print, store, or include tokens in
capsules, logs, commits, or handoffs.

Merge authority comes from the issue contract and required checks, not from
task completion alone. Protected/default branches, publishing, deployment,
destructive migrations, account changes, and physical actuation are human stops
unless explicitly authorized. Every terminal handoff names branch/worktree,
base/head, PR, scope, checks, stable review finding IDs and follow-ups,
blockers, exact next state, and a trust audit covering confidence, least-trusted
claims, untested paths, possible misunderstandings, and highest-value next
evidence.
