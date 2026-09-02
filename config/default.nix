{ inputs, ... }:
let
  networkPolicy = import ./networks.nix;
  r640Users = import ./users;
  r640Env = import ./env.nix;
  vscodeRemoteModule = import ./modules/vscode-remote.nix;
  vscodeRemote = [ vscodeRemoteModule ];
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
    inputs.home-manager.nixosModules.home-manager
    inputs.sops-nix.nixosModules.sops
    inputs.tilingDesktop.nixosModules.default
    inputs.ashes-desktop-apps.nixosModules.default
    (import ./access/module.nix)
    r640Env
    (
      { config, ... }:
      {
        nix.settings.experimental-features = [
          "nix-command"
          "flakes"
        ];
        nixpkgs.config.allowUnfree = true;
        system.stateVersion = "26.05";
        services.openssh.enable = true;
        services.openssh.settings = {
          PasswordAuthentication = false;
          KbdInteractiveAuthentication = false;
          PermitRootLogin = "prohibit-password";
        };
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
          programs.ssh = {
            enable = true;
            enableDefaultConfig = false;
            matchBlocks = config.arbor.environment.public.sshHosts;
          };
        };

        # The r640 machine identity is a narrowly scoped public grant.  The
        # matching private identity remains runtime-only on the source host.
        arbor.access.authorizedKeySets = [ "r640EvolverDeployer" ];
        users.users.ash.openssh.authorizedKeys.keys = (import ./access).r640EvolverDeployerKeys;
      }
    )
  ];
  server = [
    networkPolicy
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
    {
      arbor.access.authorizedKeySets = [
        "operator"
        "deployment"
      ];
    }
    inputs.sops-nix.nixosModules.sops
    { virtualisation.docker.enable = true; }
    r640Users
    r640Env
    vscodeRemoteModule
    serverTools
    (import ./machines/r640-0/storage.nix)
    (import ./machines/r640-0/management.nix)
  ];
  machines = inputs.arbor-manager.lib.mkMachines {
    inherit inputs;
    machinesPath = ./machines;
    profiles = {
      inherit
        desktop
        server
        r640
        vscodeRemote
        ;
    };
  };
in
{
  flake.nixosConfigurations = machines.configurations;
}
