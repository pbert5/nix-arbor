{
  inputs,
  lib,
  pkgs,
  ...
}:
{
  imports = [
    ../../sops.nix
    inputs.sops-nix.nixosModules.sops
    ../../users
  ];

  networking.hostName = "desktoptoodle";
  networking.networkmanager.enable = true;

  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      KbdInteractiveAuthentication = false;
      PermitRootLogin = "prohibit-password";
    };
  };

  services.tailscale = {
    enable = true;
    useRoutingFeatures = "client";
    extraSetFlags = [ "--accept-dns=false" ];
  };

  virtualisation.docker.enable = true;
  environment.systemPackages = with pkgs; [
    git
    gh
    curl
    wget
    jq
    ripgrep
    fd
    fzf
    tmux
    btop
    vim
    neovim
    rsync
    openssh
    nil
    nixfmt-rfc-style
    nix-tree
    nh
    tailscale
  ];

  boot.loader.systemd-boot.enable = true;
  boot.loader.systemd-boot.configurationLimit = 20;
  boot.loader.efi.canTouchEfiVariables = lib.mkDefault true;
}
