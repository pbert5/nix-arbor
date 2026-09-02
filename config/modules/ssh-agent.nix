{
  config,
  lib,
  pkgs,
  ...
}:
let
  sshHosts = config.arbor.environment.public.sshHosts;
  expectedAliases = [
    "bal-lab"
    "desktoptoodle"
    "evolver"
    "r640-0"
    "root-evolver"
  ];
  safeIdentityPath =
    path:
    lib.hasPrefix "/home/ash/.ssh/" path
    && !lib.hasInfix "*" path
    && !lib.hasInfix "?" path
    && !lib.hasInfix "PRIVATE" path;
  diagnose = pkgs.writeShellApplication {
    name = "arbor-ssh-diagnose";
    runtimeInputs = [ pkgs.openssh ];
    text = ''
      set -euo pipefail
      alias_name="''${1:-}"
      if [[ -z "$alias_name" ]]; then
        printf '%s\n' "usage: arbor-ssh-diagnose <configured-alias>" >&2
        exit 2
      fi
      if [[ -z "''${SSH_AUTH_SOCK:-}" ]]; then
        printf '%s\n' "SSH_AUTH_SOCK is not set; start the Ash user session first." >&2
        exit 1
      fi
      printf 'SSH_AUTH_SOCK=%s\n' "$SSH_AUTH_SOCK"
      ssh-add -l || true
      printf '\nEffective SSH configuration for %s (no connection attempted):\n' "$alias_name"
      ssh -G "$alias_name" | awk '$1 == "hostname" || $1 == "user" || $1 == "identityagent" || $1 == "identityfile" || $1 == "identitiesonly" { print }'
    '';
  };
in
{
  home-manager.users.ash = {
    services.ssh-agent = {
      enable = true;
      socket = "arbor-ssh-agent/socket";
    };
  };

  environment.systemPackages = [ diagnose ];

  assertions = [
    {
      assertion = config.home-manager.users.ash.services.ssh-agent.enable;
      message = "Ash must run the Home Manager SSH agent on this host.";
    }
    {
      assertion = config.home-manager.users.ash.services.ssh-agent.socket == "arbor-ssh-agent/socket";
      message = "Ash SSH agent must use the stable Arbor user-session socket.";
    }
    {
      assertion =
        lib.sort builtins.lessThan (builtins.attrNames sshHosts)
        == lib.sort builtins.lessThan expectedAliases;
      message = "Arbor SSH aliases must remain the explicit five-entry host allowlist.";
    }
    {
      assertion = lib.all (
        alias:
        let
          host = sshHosts.${alias};
        in
        host.identitiesOnly == true
        && host.identityAgent == "$SSH_AUTH_SOCK"
        && safeIdentityPath host.identityFile
      ) expectedAliases;
      message = "Arbor SSH aliases must use explicit safe identity paths and the Ash agent; no globs or private material are allowed.";
    }
  ];
}
