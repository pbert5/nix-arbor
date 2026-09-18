---
name: Workstream capsule
about: Launch one approved, independently owned workstream
title: "[WS] "
labels: ""
assignees: ""
---

<!-- Keep this issue compact: it is the owner's executable contract. Do not
     start implementation until the design and acceptance fields are complete
     and the issue is marked PROMPT_READY. -->

## State

- State: `DRAFT` / `PROMPT_READY` / `RUNNING` / `VERIFYING` / `READY_FOR_REVIEW` / `REVIEWING` / `READY_FOR_INTEGRATION` / `INTEGRATING` / `VALIDATING` / `DONE` / `BLOCKED_*`
- Parent/tracking issue: #
- Workstream owner:
- Scope boundary / shared-resource lock:

## Objective and approved design

<!-- What outcome is required, and what design was approved? -->

### Objective

### Design and approach

## Provenance

- Base branch:
- Base SHA:
- Workstream branch:
- Worktree:
- Draft PR: #
- Integration target:

## Dependencies and interfaces

- Depends on:
- Blocks:
- May modify:
- May read:
- Must not modify:
- Interfaces/shared resources:

## Acceptance and verification

- [ ] Acceptance criterion:
- [ ] Test/check contract:
- [ ] Review contract:
- [ ] Human-stop boundaries are explicit:

## Relationship bookkeeping

Use native GitHub links where supported: parent issue, sub-issues, blocked-by/blocks, duplicate, and PR development links. Record any relationship that cannot be represented natively under **Relationship audit** in the PR.

## Launch gate

- [ ] Design is approved; this issue is `PROMPT_READY`.
- [ ] Branch/worktree/base provenance is recorded.
- [ ] Ownership and exclusions are explicit.
- [ ] Dependencies and shared-resource ownership are resolved.
