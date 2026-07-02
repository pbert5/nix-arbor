{ pkgs, lib, config, ... }:
let
  serenaSource = "git+https://github.com/oraios/serena";
  transformedCodexMcpServers = lib.optionalAttrs config.programs.mcp.enable (
    lib.mapAttrs (
      name: server:
      lib.hm.mcp.transformMcpServer {
        inherit server;
        exclude = [
          "headers"
          "type"
        ];
        extraTransforms = [
          (s: s // lib.optionalAttrs (s.headers or { } != { }) { http_headers = s.headers; })
          lib.hm.mcp.addType
          (lib.hm.mcp.wrapEnvFilesCommand { inherit pkgs name; })
        ];
      }
    ) config.programs.mcp.servers
  );
  codexManagedMcpConfig =
    (pkgs.formats.toml { }).generate "codex-managed-mcp-config" {
      mcp_servers = transformedCodexMcpServers;
    };
in
{
  programs.mcp = {
    enable = true;
    servers = {
      context7.url = "https://mcp.context7.com/mcp";
      mcp-nixos.command = "${pkgs.mcp-nixos}/bin/mcp-nixos";
      serena = {
        command = "${pkgs.uv}/bin/uvx";
        args = [
          "--from"
          serenaSource
          "serena"
          "start-mcp-server"
          "--context"
          "codex"
          "--project-from-cwd"
          "--open-web-dashboard=false"
        ];
      };
    };
  };


  # mcp-nixos in home.packages so the binary is on PATH for standalone use
  # and available after the claude user registration below.
  home.packages = [
    pkgs.mcp-nixos
    pkgs.nodejs
  ];

  programs.claude-code.enableMcpIntegration = true;
  programs.codex.enableMcpIntegration = true;

  # The VSCode extension's bundled native Claude Code binary bypasses the
  # ~/.nix-profile/bin/claude wrapper that injects --plugin-dir, so MCP
  # servers declared above (context7, mcp-nixos) silently never load there
  # even though `claude` from a terminal sees them fine. Point the
  # extension at the wrapped binary so it picks up the same plugin dir.
  home.activation.vscodeClaudeProcessWrapper = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    settingsFile="$HOME/.config/Code/User/settings.json"
    if [ -f "$settingsFile" ]; then
      $DRY_RUN_CMD ${pkgs.jq}/bin/jq \
        '."claudeCode.claudeProcessWrapper" = "${config.programs.claude-code.finalPackage}/bin/claude"' \
        "$settingsFile" > "$settingsFile.tmp" \
        && $DRY_RUN_CMD mv "$settingsFile.tmp" "$settingsFile"
    fi
  '';

  # Plugin-prefixed MCP server names (plugin:claude-code-home-manager:*) produce
  # tool identifiers with colons, which Claude Code cannot forward to the model.
  # Register context7 and mcp-nixos at user scope in ~/.claude.json directly so
  # they get clean names and surface as tools in every session. The store path
  # for mcp-nixos is refreshed on each home-manager activation.
  home.activation.claudeUserMcpServers = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    claudeJson="$HOME/.claude.json"
    if [ -f "$claudeJson" ]; then
      $DRY_RUN_CMD ${pkgs.jq}/bin/jq \
        '.mcpServers["mcp-nixos"] = {"type": "stdio", "command": "${pkgs.mcp-nixos}/bin/mcp-nixos"}
         | .mcpServers["context7"] = {"type": "http", "url": "https://mcp.context7.com/mcp"}
         | if .mcpServers["serena"] then
             .mcpServers["serena"].args |= if index("--open-web-dashboard=false") then . else . + ["--open-web-dashboard=false"] end
           else . end' \
        "$claudeJson" > "$claudeJson.tmp" \
        && $DRY_RUN_CMD mv "$claudeJson.tmp" "$claudeJson"
    fi
  '';

  home.activation.serenaPluginNoDashboard = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    pluginMcpJson="$HOME/.claude/plugins/marketplaces/claude-plugins-official/external_plugins/serena/.mcp.json"
    if [ -f "$pluginMcpJson" ]; then
      $DRY_RUN_CMD ${pkgs.jq}/bin/jq \
        '.serena.args |= if index("--open-web-dashboard=false") then . else . + ["--open-web-dashboard=false"] end' \
        "$pluginMcpJson" > "$pluginMcpJson.tmp" \
        && $DRY_RUN_CMD mv "$pluginMcpJson.tmp" "$pluginMcpJson"
    fi
  '';

  # Codex profiles are not visible to every local Codex entrypoint used by the
  # VS Code extension. Keep the shared MCP registry in a small managed block in
  # the mutable base config so account switching can continue to touch only
  # auth.json.
  # Declaratively manage Codex hooks for Serena session lifecycle.
  home.file.".codex/hooks.json".source = (pkgs.formats.json { }).generate "codex-serena-hooks" {
    hooks = {
      PreToolUse = [
        {
          matcher = "Bash";
          hooks = [ { type = "command"; command = "serena-hooks remind --client=codex"; } ];
        }
      ];
      SessionStart = [
        {
          matcher = "startup|resume";
          hooks = [ { type = "command"; command = "serena-hooks activate --client=codex"; } ];
        }
      ];
      Stop = [
        {
          hooks = [ { type = "command"; command = "serena-hooks cleanup --client=codex"; } ];
        }
      ];
    };
  };

  # Enable Codex hooks feature flag so hooks.json is loaded.
  home.activation.codexHooksFeature = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    configFile="$HOME/.codex/config.toml"
    $DRY_RUN_CMD mkdir -p "$HOME/.codex"
    if [ ! -e "$configFile" ]; then
      $DRY_RUN_CMD install -m 0600 /dev/null "$configFile"
    fi
    if ! ${pkgs.gnugrep}/bin/grep -q 'codex_hooks' "$configFile"; then
      $DRY_RUN_CMD ${pkgs.coreutils}/bin/printf '\n[features]\ncodex_hooks = true\n' >> "$configFile"
    fi
  '';

  home.activation.codexManagedMcpConfig = lib.hm.dag.entryAfter [ "codexMutableConfig" ] ''
    configFile="$HOME/.codex/config.toml"
    managedFile="${codexManagedMcpConfig}"
    begin="# BEGIN nix-managed mcp servers"
    end="# END nix-managed mcp servers"

    $DRY_RUN_CMD mkdir -p "$HOME/.codex"
    if [ ! -e "$configFile" ]; then
      $DRY_RUN_CMD install -m 0600 /dev/null "$configFile"
    fi

    tmpFile="$configFile.tmp"
    $DRY_RUN_CMD ${pkgs.gawk}/bin/awk \
      -v begin="$begin" \
      -v end="$end" \
      'index($0, begin) == 1 { skip = 1; next }
       index($0, end) == 1 { skip = 0; next }
       !skip { print }' \
      "$configFile" > "$tmpFile"
    $DRY_RUN_CMD ${pkgs.coreutils}/bin/printf '\n%s\n' "$begin" >> "$tmpFile"
    $DRY_RUN_CMD ${pkgs.coreutils}/bin/cat "$managedFile" >> "$tmpFile"
    $DRY_RUN_CMD ${pkgs.coreutils}/bin/printf '%s\n' "$end" >> "$tmpFile"
    $DRY_RUN_CMD mv "$tmpFile" "$configFile"
  '';
}
