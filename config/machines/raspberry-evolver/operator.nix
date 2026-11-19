{
  inputs,
  pkgs,
  ...
}:
{
  imports = [ ../../modules/vscode-remote.nix ];

  virtualisation.docker = {
    enable = true;
    daemon.settings = {
      shutdown-timeout = 45;
      log-driver = "local";
      log-opts = {
        max-size = "10m";
        max-file = "3";
      };
    };
  };
  users.users.ash.extraGroups = [ "docker" ];
  environment.systemPackages = with pkgs; [
    bash
    btop
    curl
    devcontainer
    docker-compose
    fd
    fzf
    gh
    git
    jq
    openssl
    python3
    ripgrep
    tmux
    unzip
    usbutils
    util-linux
    vim
    wget
    zoxide
    inputs.codex-nixpkgs.legacyPackages.${stdenv.hostPlatform.system}.codex
  ];
  programs.bash.interactiveShellInit = ''
    eval "$(${pkgs.zoxide}/bin/zoxide init bash)"
  '';
}
