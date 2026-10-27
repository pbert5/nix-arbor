# GitHub workstream ledger

This repository uses GitHub issues and pull requests as the durable ledger for
substantial work. Templates reduce omissions; they do not replace the issue's
authoritative contract or human-stop boundaries.

## Checkpoint and terminal handoff

Post meaningful checkpoints and the final handoff on the tracking issue and
workstream PR. Use this packet, keeping claims compact and evidence-backed:

```text
Checkpoint: <UTC timestamp>; state=<state>
Branch/worktree: <branch>; <worktree path>
Base/head: <base branch and SHA>; <head SHA>
PR: #<number> (draft|ready|none)
Scope: <completed scope and explicit exclusions>
Checks: <commands and results/evidence>
Findings/followups: <RF IDs, or none>
Blockers: <none or exact blocker/state>
Next state: <one deterministic state>
Trust audit: confidence=<high|medium|low>; least-trusted=<claims>; untested=<paths>; possible misunderstanding=<text>; next evidence=<text>
```

Routine status pings are not checkpoints. A terminal handoff must identify the
exact next state and preserve open findings rather than silently closing them.

## Review findings

Substantive findings use stable, append-only IDs (`RF-001`, `RF-002`, ...)
within the review ledger. Each finding records severity and blocking rationale,
evidence, affected SHA, disposition, and verification. A later review appends
to the same ID or adds a new ID; it does not renumber or delete history.

Allowed review results are `PASS`, `PASS_WITH_FOLLOWUPS`, and
`CHANGES_REQUIRED`. Use `PASS_WITH_FOLLOWUPS` when the reviewed head is safe to
integrate but follow-up work remains explicitly owned and linked.

## Branch and PR provenance

Every workstream records its base branch/SHA, workstream branch, worktree, head
SHA, draft PR, and integration target. Refresh head SHA and validation evidence
after repair commits. A draft PR is the normal durable handoff; integration is
authority-based and must not imply deployment, release, hardware actuation, or
protected-branch permission.

## Relationship realization

Prose intent is not sufficient. The tracking owner designates a read-only
relationship auditor before final completion. The auditor compares the issue
and PR prose with native GitHub state and records discrepancies, including
missing parent/sub-issue links, blocks/blocked-by links, duplicate links, or PR
development links. Reconcile through native controls where supported; retain
unsupported relationship notes in the tracking issue and link them to the
affected issue/PR. Record the evidence date and commit/PR SHA.

## Labels

`bug` is the canonical bug label. Agent-created bug issues use it when the
label is available. If it is absent or permissions prevent adding it, state
that fact in the issue and request maintainer triage; do not create a synonym.
