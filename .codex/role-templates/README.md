# Personal Codex role templates

The files in this directory are reusable role templates, not project policy.
Install or merge them into the user's `CODEX_HOME/agents/` directory and
register them from the user's `CODEX_HOME/config.toml` with an
`[agents.<name>]` entry whose `config_file` points at the installed file.
Merge individual entries; do not replace unrelated personal configuration.

These templates intentionally contain no credentials, account state, model
choice, approval policy, sandbox policy, or project paths. Keep those settings
in personal configuration or the active project contract.

For substantial work, the primary executor should reserve capacity for
depth-2 delegation before launching first-order owners. If the live runtime
cap is not observable, use the runtime default and do not infer a quota from
this repository. Supervision is passive-first: observe lifecycle and existing
output, and intervene only for an unblock, changed constraint, safety issue,
clarification request, or scope/resource conflict.
