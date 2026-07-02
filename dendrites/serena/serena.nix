{ pkgs, ... }:
let
  # Serena (https://github.com/oraios/serena) has no nixpkgs package yet, so
  # run it the way upstream documents: via `uv` straight from its git repo.
  serena = pkgs.writeShellScriptBin "serena" ''
    exec ${pkgs.uv}/bin/uvx --from git+https://github.com/oraios/serena serena "$@"
  '';
  # serena-hooks is a separate entrypoint in the same package, used by Claude
  # Code and Codex hooks for session activation, remind, and cleanup.
  serena-hooks = pkgs.writeShellScriptBin "serena-hooks" ''
    exec ${pkgs.uv}/bin/uvx --from git+https://github.com/oraios/serena serena-hooks "$@"
  '';
in
{
  environment.systemPackages = [
    pkgs.nodejs
    serena
    serena-hooks
  ];
}
