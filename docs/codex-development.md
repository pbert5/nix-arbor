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
