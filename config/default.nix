{ inputs, ... }:
let
  networkPolicy = import ./networks.nix;
  r640Users = import ./users;
  environment = import ./env.nix;
  r640Sops = import ./sops.nix;
  vscodeRemote = import ./modules/vscode-remote.nix;
  registryServiceContract =
    if builtins.hasAttr "service-contract" inputs.arbor-registry.nixosModules then
      inputs.arbor-registry.nixosModules.service-contract
    else
      # Compatibility for locks predating the exported module; input wins as
      # soon as the Registry input publishes the service-contract export.
      import ../packages/arbor-registry/modules/service-contract.nix;
  serverTools =
    { pkgs, ... }:
    {
      environment.systemPackages = with pkgs; [
        git
        gh
        curl
        wget
        jq
        yq-go
        ripgrep
        fd
        fzf
        tmux
        btop
        vim
        neovim
        rsync
        openssh
        nixfmt-rfc-style
        nil
        nix-tree
        nh
        tailscale
        zfs
        pkgs.codex
        inputs.codex-switch.packages.${pkgs.system}.codex-switch
        rtk
      ];
    };
  desktop = [
    networkPolicy
    environment
    inputs.home-manager.nixosModules.home-manager
    inputs.tilingDesktop.nixosModules.default
    inputs.ashes-desktop-apps.nixosModules.default
    {
      nix.settings.experimental-features = [
        "nix-command"
        "flakes"
      ];
      nixpkgs.config.allowUnfree = true;
      system.stateVersion = "26.05";
      users.users.ash = {
        isNormalUser = true;
        description = "Ash";
        extraGroups = [
          "networkmanager"
          "wheel"
        ];
      };
      home-manager.useGlobalPkgs = true;
      home-manager.useUserPackages = true;
      home-manager.users.ash = {
        imports = [
          inputs.ashzsh.homeModules.default
          inputs.tilingDesktop.homeModules.hyprland
          inputs.ashes-desktop-apps.homeModules.default
        ];
        home.stateVersion = "26.05";
        home.username = "ash";
        home.homeDirectory = "/home/ash";
        ashesDesktopApps = {
          enable = true;
          sets = [ "desktop.core" ];
        };
      };
    }
  ];
  server = [
    networkPolicy
    environment
    inputs.home-manager.nixosModules.home-manager
    {
      nix.settings.experimental-features = [
        "nix-command"
        "flakes"
      ];
      system.stateVersion = "26.05";
      services.openssh.enable = true;
      services.openssh.settings = {
        PasswordAuthentication = false;
        KbdInteractiveAuthentication = false;
        PermitRootLogin = "prohibit-password";
      };
      home-manager.useGlobalPkgs = true;
      home-manager.useUserPackages = true;
    }
  ];
  r640 = [
    (import ./access/module.nix)
    { arbor.access.authorizedKeySets = [ "operator" "deployment" ]; }
    inputs.sops-nix.nixosModules.sops
    { virtualisation.docker.enable = true; }
    r640Users
    r640Sops
    vscodeRemote
    serverTools
    (import ./machines/r640-0/storage.nix)
    (import ./machines/r640-0/management.nix)
  ];
  arborParticipant = [
    inputs.arbor-registry.nixosModules.default
    registryServiceContract
    {
      # This is a public policy/status boundary only. Runtime credentials,
      # initialization, and unseal remain explicit operator actions.
      cluster.registry.enable = true;
      cluster.registry.runtime.enable = true;
    }
  ];
  machines = inputs.arbor-manager.lib.mkMachines {
    inherit inputs;
    machinesPath = ./machines;
    profiles = {
      inherit
        arborParticipant
        desktop
        server
        r640
        ;
    };
  };
in
{
  flake.nixosConfigurations = machines.configurations;
}
