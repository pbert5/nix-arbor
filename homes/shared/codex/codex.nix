{ config, lib, pkgs, ... }:
let
  unstablePkgs = if pkgs ? unstable then pkgs.unstable else pkgs;
  upstreamCodex = unstablePkgs.codex;
  transformedMcpServers = lib.optionalAttrs config.programs.mcp.enable (
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

  codexNixSettings = {
    projects."/work/flake".trust_level = "trusted";
  } // lib.optionalAttrs (transformedMcpServers != { }) {
    mcp_servers = transformedMcpServers;
  };
in
{
  home.packages = [
    pkgs.codex-switch
  ];

  programs.codex = {
    enable = true;
    enableMcpIntegration = lib.mkForce false;
    package = upstreamCodex;
    settings = { };
  };

  home.file.".codex/nix.config.toml".source =
    (pkgs.formats.toml { }).generate "codex-nix-config" codexNixSettings;

  home.file.".codex/RTK.md".text = ''
    # RTK - Rust Token Killer (Codex CLI)

    **Usage**: Token-optimized CLI proxy for shell commands.

    ## Rule

    Always prefix shell commands with `rtk`.

    Examples:

    ```bash
    rtk git status
    rtk cargo test
    rtk npm run build
    rtk pytest -q
    ```

    ## Meta Commands

    ```bash
    rtk gain            # Token savings analytics
    rtk gain --history  # Recent command savings history
    rtk proxy <cmd>     # Run raw command without filtering
    ```

    ## Verification

    ```bash
    rtk --version
    rtk gain
    which rtk
    ```
  '';

  home.file.".codex/AGENTS.md".text = "@/home/example/.codex/RTK.md\n";

  home.activation.codexMutableConfig = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    $DRY_RUN_CMD mkdir -p "$HOME/.codex"
    if [ -L "$HOME/.codex/config.toml" ]; then
      $DRY_RUN_CMD rm "$HOME/.codex/config.toml"
    fi
    if [ ! -e "$HOME/.codex/config.toml" ]; then
      $DRY_RUN_CMD install -m 0600 /dev/null "$HOME/.codex/config.toml"
    fi
  '';
}
