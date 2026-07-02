{ pkgs, lib, ... }:
let
  codex = pkgs.unstable.codex;

  testScript = pkgs.writeShellApplication {
    name = "codex-hourly-test";
    runtimeInputs = [ codex ];
    text = ''
      tmp="$(mktemp -d)"
      trap 'rm -rf "$tmp"' EXIT

      # --ignore-user-config prevents MCP activation (halves cost vs mcp_servers={})
      try() {
        codex exec \
          --cd "$tmp" \
          --ignore-user-config \
          --ignore-rules \
          --ephemeral \
          --skip-git-repo-check \
          "$@" \
          'Run exactly this shell command and nothing else: rtk fastfetch'
      }

      COST_FLAGS=(
        -c 'approval_policy="never"'
        -c 'model_reasoning_effort="low"'
        -c 'model_reasoning_summary="none"'
        -c 'model_verbosity="low"'
      )

      for MODEL in gpt-5.4-mini gpt-5.4 gpt-5.5; do
        try -m "$MODEL" "''${COST_FLAGS[@]}" && exit 0
      done

      # No -m: let codex pick
      try "''${COST_FLAGS[@]}" && exit 0

      # No reasoning flags either
      try -c 'approval_policy="never"' && exit 0

      echo "WARNING: codex-hourly-test: all attempts failed — fruit may be out of date" >&2
      exit 0
    '';
  };
in
{
  systemd.services.codex-hourly-test = {
    description = "Hourly Codex GPT model liveness test";
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    serviceConfig = {
      Type = "oneshot";
      User = "ash";
      Environment = [
        "HOME=/home/example"
        # rtk and fastfetch live in the user profile; codex inherits this PATH for shell tool calls
        "PATH=/etc/profiles/per-user/ash/bin:/run/current-system/sw/bin"
      ];
      ExecStart = lib.getExe testScript;
    };
  };

  systemd.timers.codex-hourly-test = {
    description = "Hourly Codex GPT model liveness test timer";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnCalendar = "hourly";
      Persistent = true;
    };
  };
}
