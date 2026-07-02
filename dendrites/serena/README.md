# `serena`

System-level access to the [Serena](https://github.com/oraios/serena) coding-agent MCP server.

## Purpose

Serena has no nixpkgs package, so this dendrite provides a `serena` wrapper
that runs it via `uv` straight from its upstream git repo, matching the
invocation upstream documents.

## Main Effects

Adds a `serena` command to `environment.systemPackages` that proxies to:

```
uvx --from git+https://github.com/oraios/serena serena "$@"
```

## MCP server registration

The shared Home Manager MCP registry declares the Serena server in
[`homes/shared/mcp/mcp.nix`](../../homes/shared/mcp/mcp.nix). Codex and Claude
Code pick it up through their `enableMcpIntegration` settings, so there is no
separate `claude mcp add` or Codex config edit for this repo's managed users.

The server is launched as:

```
uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context codex --project-from-cwd
```

## Selection

Opt-in per host; not part of any role by default.
