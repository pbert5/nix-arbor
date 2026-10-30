{ config, pkgs, ... }:
let
  runnerUser = "arbor-github-runner";
  runnerGroup = "arbor-github-runner";
  tokenPath = "/var/lib/arbor-secrets/github-runners/meta-bal.token";
in
{
  users.groups.${runnerGroup} = { };
  users.users.${runnerUser} = {
    isSystemUser = true;
    group = runnerGroup;
    extraGroups = [ "docker" ];
    description = "Meta BAL GitHub Actions runner";
  };

  # The token is provisioned by an operator. Nix only owns the parent
  # directory; the token value never enters the evaluation or store.
  systemd.tmpfiles.rules = [
    "d /var/lib/arbor-secrets 0700 root root - -"
    "d /var/lib/arbor-secrets/github-runners 0700 root root - -"
  ];

  services.github-runners.meta-bal = {
    enable = true;
    url = "https://github.com/pbert5/meta_bal";
    name = "r640-0-meta-bal";
    count = 1;
    extraLabels = [
      "r640-0"
      "meta-bal"
    ];
    tokenFile = tokenPath;
    ephemeral = true;
    user = runnerUser;
    group = runnerGroup;

    # These are the host-side tools used before Meta BAL's Dev Container is
    # started by its workflow. Project Python dependencies stay in the
    # container.
    extraPackages = with pkgs; [
      curl
      docker-client
      nodejs
      python3
    ];

    # Docker's Unix socket uses the host docker group. PrivateUsers would
    # remap the runner identity and make that explicit access ineffective.
    serviceOverrides = {
      PrivateUsers = false;
      SupplementaryGroups = [ "docker" ];
    };
  };

  assertions = [
    {
      assertion = config.services.github-runners.meta-bal.count == 1;
      message = "The Meta BAL runner must remain a single r640-0 instance";
    }
    {
      assertion = config.services.github-runners.meta-bal.url == "https://github.com/pbert5/meta_bal";
      message = "The Meta BAL runner must remain repository-scoped";
    }
    {
      assertion = config.services.github-runners.meta-bal.ephemeral;
      message = "The Meta BAL runner must remain ephemeral";
    }
    {
      assertion = config.services.github-runners.meta-bal.tokenFile == tokenPath;
      message = "The Meta BAL runner token must remain at the runtime-only secret path";
    }
  ];
}
