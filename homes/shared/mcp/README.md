# `shared/mcp`

Shared MCP (Model Context Protocol) server registry for Claude Code and Codex.

## Purpose

Declares MCP servers once, in [`mcp.nix`](mcp.nix), via home-manager's
`programs.mcp.servers`. `enableMcpIntegration` on both `programs.claude-code`
and `programs.codex` (set here) feeds that shared list into each client's
own config, so a server only needs to be added in one place.

## Adding a server

Edit `servers` in [`mcp.nix`](mcp.nix):

```nix
programs.mcp.servers = {
  # remote (HTTP/SSE) server
  context7.url = "https://mcp.context7.com/mcp";

  # local (stdio) server backed by a nixpkgs package
  mcp-nixos.command = "${pkgs.mcp-nixos}/bin/mcp-nixos";

  # local server launched through a Nix-provided runner
  serena = {
    command = "${pkgs.uv}/bin/uvx";
    args = [
      "--from"
      "git+https://github.com/oraios/serena"
      "serena"
      "start-mcp-server"
      "--context"
      "codex"
      "--project-from-cwd"
    ];
  };

  # local server needing args/env
  example = {
    command = "npx";
    args = [ "-y" "@modelcontextprotocol/server-everything" ];
    env.MY_API_KEY.file = "/run/secrets/my_api_key";
  };
};
```

Then rebuild (`nixos-rebuild switch` for `user1`/`user2`, since these users
are managed via `home-manager.users.*` inside the NixOS system, not a
standalone home-manager generation).

## How each client picks it up

- **Codex**: home-manager writes the merged server list into the managed
  `~/.codex/nix.config.toml` profile (`mcp_servers.*`). It also stamps the same
  list into a clearly marked managed block in mutable `~/.codex/config.toml`,
  because some local Codex entrypoints used by the VS Code extension do not
  consistently load named profiles. The managed block leaves Codex free to
  persist interactive trust decisions in `~/.codex/config.toml`, while Codex
  Switch can continue to manage only `auth.json`.

- **Claude Code**: home-manager does *not* touch the mutable
  `~/.claude/settings.json`. Instead it wraps the `claude` binary itself with
  `--plugin-dir <nix store path>`, where that plugin directory contains a
  generated `.mcp.json` with the merged servers. This means:
  - the servers are baked into the wrapped binary at build time
  - an **already-running** `claude` session keeps using the `--plugin-dir`
    it started with — start a new session (or run `claude` again in a fresh
    shell) to pick up changes
  - no manual `claude mcp add` step is needed; this is the declarative
    alternative to imperative `claude mcp add` commands.

## Selection

Wired into `homes/shared/workstation/workstation.nix`, so it applies to any
user importing `shared/workstation` (currently `user1` and `user2`).
