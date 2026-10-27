@AGENTS.md

Claude Code notes:

- Start from a dedicated worktree and confirm `git status` before editing.
- Use the Nix specialist and integration-test roles in `.claude/agents/` when
  the current Claude runtime supports them. Keep architecture and integration
  decisions in the assigned task owner; do not assume Codex-specific settings.
- Review another agent's branch by inspecting its diff and validation before
  merging or cherry-picking it.
- When the task is complete and validation passes, merge into the identified
  base branch, verify the merged result, then remove the clean worktree and
  stale merged local agent branch. Report a committed handoff instead when
  review, coordination, conflicts, approval, or failing validation prevents a
  safe merge.
